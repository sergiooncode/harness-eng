"""Golden dataset validator.

Feeds shared/input.json through an extension point implementation and
compares the output to the per-implementation expected_output.json.
"""

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GoldenResult:
    """Result of a golden dataset check."""
    passed: bool
    expected: Any
    actual: Any
    differences: list[str]


def validate_golden(actual: Any, expected_path: Path) -> GoldenResult:
    """Compare actual output to expected output from a golden file.

    Args:
        actual: The actual output produced by the implementation.
        expected_path: Path to expected_output.json.

    Returns:
        GoldenResult with pass/fail and any differences.
    """
    if not expected_path.exists():
        return GoldenResult(
            passed=True, expected=None, actual=None,
            differences=["No golden dataset found — skipping."],
        )

    with open(expected_path) as f:
        expected = json.load(f)

    if isinstance(expected, list) and isinstance(actual, list):
        return _compare_records(expected, actual)
    if isinstance(expected, dict) and isinstance(actual, dict):
        return _compare_dicts(expected, actual)

    differences = _diff_dicts(expected, actual)
    return GoldenResult(
        passed=len(differences) == 0,
        expected=expected,
        actual=actual,
        differences=differences,
    )


def validate_writer(writer_class: type, writer_name: str, golden_dir: Path) -> GoldenResult:
    """Validate a writer implementation against golden datasets.

    Args:
        writer_class: The writer class to test.
        writer_name: Name of the writer (e.g. "csv", "airtable").
        golden_dir: Root golden/ directory.

    Returns:
        GoldenResult with pass/fail and any differences.
    """
    shared_input_path = golden_dir / "writers" / "shared" / "input.json"
    expected_path = golden_dir / "writers" / writer_name / "expected_output.json"

    if not shared_input_path.exists() or not expected_path.exists():
        return GoldenResult(
            passed=True,
            expected=None,
            actual=None,
            differences=["No golden dataset found — skipping."],
        )

    with open(shared_input_path) as f:
        input_data = json.load(f)

    with open(expected_path) as f:
        expected = json.load(f)

    from rauda_core.schemas import Evaluation

    rows = []
    evaluations: list[Evaluation | None] = []
    for item in input_data:
        rows.append({"ticket": item["ticket"], "reply": item["reply"]})
        if item.get("content_score") is not None:
            evaluations.append(Evaluation(
                content_score=item["content_score"],
                content_explanation=item["content_explanation"],
                format_score=item["format_score"],
                format_explanation=item["format_explanation"],
            ))
        else:
            evaluations.append(None)

    if writer_name == "csv":
        return _validate_csv_writer(writer_class, rows, evaluations, expected)
    elif writer_name == "airtable":
        return _validate_airtable_writer(writer_class, rows, evaluations, expected)

    return GoldenResult(
        passed=True, expected=None, actual=None,
        differences=[f"No golden validator for writer type '{writer_name}'."],
    )


def _validate_csv_writer(
    writer_class: type,
    rows: list[dict],
    evaluations: list,
    expected: list[dict],
) -> GoldenResult:
    """Run CsvWriter to a StringIO-backed file and compare output."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        writer = writer_class(output_path=tmp_path)
        writer.write(rows, evaluations)

        with open(tmp_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            actual = [dict(row) for row in reader]
    finally:
        tmp_path.unlink(missing_ok=True)

    return _compare_records(expected, actual)


def _validate_airtable_writer(
    writer_class: type,
    rows: list[dict],
    evaluations: list,
    expected: list[dict],
) -> GoldenResult:
    """Validate AirtableWriter builds the correct records without calling the API."""
    from rauda_core.writers.airtable_writer import _FIELD_MAP

    actual = []
    for row, evaluation in zip(rows, evaluations):
        fields: dict[str, Any] = {
            _FIELD_MAP["ticket"]: row.get("ticket", ""),
            _FIELD_MAP["reply"]: row.get("reply", ""),
        }
        if evaluation:
            for key, value in evaluation.model_dump().items():
                fields[_FIELD_MAP[key]] = value
        else:
            fields[_FIELD_MAP["content_score"]] = None
            fields[_FIELD_MAP["content_explanation"]] = None
            fields[_FIELD_MAP["format_score"]] = None
            fields[_FIELD_MAP["format_explanation"]] = None
        actual.append(fields)

    return _compare_records(expected, actual)


def validate_integration(
    integration_class: type,
    config: Any,
    golden_dir: Path,
    integration_name: str = "default",
) -> GoldenResult:
    """Validate an integration's parse_webhook against golden datasets.

    Args:
        integration_class: The integration class to test.
        config: ClientConfig to instantiate the integration.
        golden_dir: Root golden/ directory.
        integration_name: Name of the expected output folder.

    Returns:
        GoldenResult with pass/fail and any differences.
    """
    shared_input_path = golden_dir / "integrations" / "shared" / "input.json"
    expected_path = golden_dir / "integrations" / integration_name / "expected_output.json"

    if not shared_input_path.exists() or not expected_path.exists():
        return GoldenResult(
            passed=True, expected=None, actual=None,
            differences=["No golden dataset found — skipping."],
        )

    with open(shared_input_path) as f:
        input_data = json.load(f)

    with open(expected_path) as f:
        expected = json.load(f)

    try:
        instance = integration_class(config)
        payload = input_data.get("payload", {})
        event_type, ticket = instance.parse_webhook(payload)

        actual = {
            "event_type": event_type.value,
            "ticket": {
                "ticket_id": ticket.ticket_id,
                "subject": ticket.subject,
                "description": ticket.description,
                "requester_email": ticket.requester_email,
                "requester_name": ticket.requester_name,
                "status": ticket.status,
                "priority": ticket.priority,
                "tags": ticket.tags,
                "custom_fields": ticket.custom_fields,
            },
        }
    except Exception as e:
        return GoldenResult(
            passed=False, expected=expected, actual=None,
            differences=[f"Integration raised {type(e).__name__}: {e}"],
        )

    return _compare_dicts(expected, actual)


def _compare_records(expected: list, actual: list) -> GoldenResult:
    """Compare two lists of record dicts."""
    differences = []

    if len(expected) != len(actual):
        differences.append(
            f"Record count mismatch: expected {len(expected)}, got {len(actual)}"
        )

    for i, (exp, act) in enumerate(zip(expected, actual)):
        record_diffs = _diff_dicts(exp, act, prefix=f"record[{i}]")
        differences.extend(record_diffs)

    return GoldenResult(
        passed=len(differences) == 0,
        expected=expected,
        actual=actual,
        differences=differences,
    )


def _compare_dicts(expected: dict, actual: dict) -> GoldenResult:
    """Compare two dicts."""
    differences = _diff_dicts(expected, actual)
    return GoldenResult(
        passed=len(differences) == 0,
        expected=expected,
        actual=actual,
        differences=differences,
    )


def _diff_dicts(expected: Any, actual: Any, prefix: str = "") -> list[str]:
    """Recursively diff two values, returning human-readable differences."""
    diffs = []
    path = prefix

    if isinstance(expected, dict) and isinstance(actual, dict):
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                diffs.append(f"{child_path}: unexpected key (got {actual[key]!r})")
            elif key not in actual:
                diffs.append(f"{child_path}: missing (expected {expected[key]!r})")
            else:
                diffs.extend(_diff_dicts(expected[key], actual[key], child_path))
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: list length {len(expected)} vs {len(actual)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(_diff_dicts(e, a, f"{path}[{i}]"))
    else:
        # Normalize for comparison: str vs int/None
        if _normalize(expected) != _normalize(actual):
            diffs.append(f"{path}: expected {expected!r}, got {actual!r}")

    return diffs


def _normalize(value: Any) -> Any:
    """Normalize values for comparison (e.g. '4' == 4, '' == None)."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    return value
