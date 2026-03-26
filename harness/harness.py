"""
harness/harness.py — The engineering harness for AI-agent-driven development.

This is the SINGLE ENTRY POINT that an AI agent (Claude Code, Cursor, etc.)
invokes to validate its own work. The agent runs this, reads the structured
JSON output, and uses it to self-correct.

Usage by an AI agent:
    python -m harness.harness check clients/new_client/
    python -m harness.harness check-all clients/
    python -m harness.harness eval --spec spec.md --target clients/new_client/

The output is ALWAYS structured JSON so the agent can parse it programmatically.
The error messages are ACTIONABLE — they tell the agent exactly what to fix.
"""

import json
import sys
from pathlib import Path
from typing import Any

from harness.validators.schema_validator import ConfigValidator, WorkflowValidator
from harness.validators.structural_linter import StructuralLinter
from harness.validators.consistency_checker import ConsistencyChecker
from harness.validators.golden_validator import validate_writer, validate_integration
from harness.evals.spec_compliance import SpecComplianceEvaluator

# ------------------------------------------------------------------
# Validator registry — one entry per client artifact type.
# Adding a new extension point = adding one line here.
# ------------------------------------------------------------------
CLIENT_VALIDATORS: dict[str, Any] = {
    "config.yaml": ConfigValidator(),
    "integration.py": StructuralLinter(
        base_class_name="BaseIntegration",
        required_methods={"validate_webhook", "parse_webhook", "enrich_context", "execute_action"},
    ),
    "workflow.yaml": WorkflowValidator(),
}


class Harness:
    """The harness the AI agent runs against its own output."""

    def __init__(self):
        self.consistency_checker = ConsistencyChecker()
        self.spec_evaluator = SpecComplianceEvaluator()

    def check_client(self, client_dir: Path) -> dict[str, Any]:
        """Run all harness checks on a single client.

        Scans the client directory and runs every registered validator
        against matching files. No per-artifact branching.
        """
        client_dir = Path(client_dir)
        result: dict[str, Any] = {
            "client": client_dir.name,
            "passed": True,
            "checks": {},
            "summary": "",
            "next_steps": [],
        }

        # Pre-check: directory and config.yaml must exist
        if not client_dir.exists():
            result["passed"] = False
            result["checks"]["structure"] = {
                "passed": False,
                "issues": [f"Directory {client_dir} does not exist. Create it first."],
            }
            result["summary"] = "Missing files. See next_steps."
            result["next_steps"] = result["checks"]["structure"]["issues"]
            return result

        config_path = client_dir / "config.yaml"
        if not config_path.exists():
            result["passed"] = False
            result["checks"]["structure"] = {
                "passed": False,
                "issues": [
                    f"Missing {config_path}. Create config.yaml following the schema in "
                    f"rauda_core/schemas.py — see ClientConfig dataclass for all required fields."
                ],
            }
            result["summary"] = "Missing files. See next_steps."
            result["next_steps"] = result["checks"]["structure"]["issues"]
            return result

        # Run every registered validator against matching files
        for filename, validator in CLIENT_VALIDATORS.items():
            filepath = client_dir / filename
            if filepath.exists():
                result["checks"][filename] = validator.validate(filepath)
                if not result["checks"][filename]["passed"]:
                    result["passed"] = False

        # Try to load the integration
        integration_path = client_dir / "integration.py"
        load_result = self._try_load(client_dir, config_path, integration_path)
        result["checks"]["load"] = load_result
        if not load_result["passed"]:
            result["passed"] = False

        # Golden dataset behavioral check
        if load_result["passed"]:
            golden_dir = Path(__file__).resolve().parent.parent / "golden"
            golden_result = self._check_integration_golden(
                config_path, integration_path, golden_dir,
            )
            result["checks"]["golden"] = golden_result
            if not golden_result["passed"]:
                result["passed"] = False

        # Build summary and next_steps
        result["summary"] = self._build_summary(result)
        result["next_steps"] = self._build_next_steps(result)

        return result

    def check_all(self, clients_dir: Path) -> dict[str, Any]:
        """Run harness on all clients + cross-client consistency + writer checks."""
        clients_dir = Path(clients_dir)
        result: dict[str, Any] = {
            "passed": True,
            "clients": {},
            "writers": {},
            "consistency": {},
            "summary": "",
        }

        # Check each client
        if clients_dir.exists():
            for client_dir in sorted(clients_dir.iterdir()):
                if client_dir.is_dir() and not client_dir.name.startswith("."):
                    client_result = self.check_client(client_dir)
                    result["clients"][client_dir.name] = client_result
                    if not client_result["passed"]:
                        result["passed"] = False

        # Auto-discover and validate writers
        golden_dir = Path(__file__).resolve().parent.parent / "golden"
        writer_linter = StructuralLinter(
            base_class_name="ResultWriter",
            required_methods={"write"},
        )
        writers_dir = Path(__file__).resolve().parent.parent / "rauda_core" / "writers"
        if writers_dir.exists():
            for py_file in sorted(writers_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue

                lint_result = writer_linter.validate(py_file)
                golden_result = self._check_writer_golden(py_file, py_file.stem.removesuffix("_writer"), golden_dir)

                writer_passed = lint_result["passed"] and golden_result["passed"]
                result["writers"][py_file.stem] = {
                    **lint_result,
                    "golden": golden_result,
                    "passed": writer_passed,
                }
                if not writer_passed:
                    result["passed"] = False

        # Cross-client consistency
        consistency_issues = self.consistency_checker.check_all(clients_dir)
        result["consistency"] = {
            "passed": not any(i.severity == "error" for i in consistency_issues),
            "issues": [
                {"client": i.client, "category": i.category, "message": i.message, "severity": i.severity}
                for i in consistency_issues
            ],
        }

        # Summary
        total_clients = len(result["clients"])
        passed_clients = sum(1 for c in result["clients"].values() if c["passed"])
        total_writers = len(result["writers"])
        passed_writers = sum(1 for w in result["writers"].values() if w["passed"])
        result["summary"] = (
            f"{passed_clients}/{total_clients} clients passed, "
            f"{passed_writers}/{total_writers} writers passed."
        )

        return result

    def eval_spec(self, spec_path: str, target_path: str) -> dict[str, Any]:
        """Verify implementation against challenge spec. Agent calls this to check its own work."""
        return self.spec_evaluator.evaluate_from_paths(Path(spec_path), Path(target_path))

    def _try_load(self, client_dir: Path, config_path: Path, integration_path: Path) -> dict:
        """Try to actually import and instantiate the integration."""
        try:
            from rauda_core.integrations.registry import load_config_from_yaml, load_integration_class
            from rauda_core.integrations.default import DefaultIntegration
            config = load_config_from_yaml(config_path)
            if integration_path.exists():
                cls = load_integration_class(integration_path)
            else:
                cls = DefaultIntegration
            instance = cls(config)
            return {
                "passed": True,
                "integration_class": cls.__name__,
                "message": f"Successfully loaded {cls.__name__} with config '{config.client_name}'",
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "fix_hint": (
                    f"The integration failed to load: {e}. "
                    f"Check that config.yaml values match the schema enums "
                    f"and that integration.py imports are correct."
                ),
            }

    def _check_writer_golden(self, py_file: Path, writer_name: str, golden_dir: Path) -> dict:
        """Run a writer against its golden dataset."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("_writer_mod", py_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Find the ResultWriter subclass
            from rauda_core.interfaces.writer import ResultWriter
            writer_cls = None
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, ResultWriter) and obj is not ResultWriter:
                    writer_cls = obj
                    break

            if writer_cls is None:
                return {"passed": True, "message": "No ResultWriter subclass found — skipping golden."}

            result = validate_writer(writer_cls, writer_name, golden_dir)
            return {
                "passed": result.passed,
                "differences": result.differences,
            }
        except Exception as e:
            return {
                "passed": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def _check_integration_golden(
        self, config_path: Path, integration_path: Path, golden_dir: Path,
    ) -> dict:
        """Run an integration against its golden dataset.

        Golden checks only run when a matching expected_output.json exists:
        - Custom integration in clients/<slug>/integration.py → golden/integrations/<slug>/
        - Config-only client using DefaultIntegration → golden/integrations/default/
        """
        try:
            from rauda_core.integrations.registry import load_config_from_yaml, load_integration_class
            from rauda_core.integrations.default import DefaultIntegration

            config = load_config_from_yaml(config_path)
            client_slug = config_path.parent.name
            if integration_path.exists():
                cls = load_integration_class(integration_path)
            else:
                cls = DefaultIntegration

            # Golden checks are per-client: only run when golden/integrations/<slug>/ exists
            expected_path = golden_dir / "integrations" / client_slug / "expected_output.json"
            if not expected_path.exists():
                return {
                    "passed": True,
                    "message": f"No golden dataset at {expected_path.relative_to(golden_dir)} — skipping.",
                }

            # Derive the golden folder name from the expected_path
            integration_name = expected_path.parent.name
            result = validate_integration(cls, config, golden_dir, integration_name)
            return {
                "passed": result.passed,
                "differences": result.differences,
            }
        except Exception as e:
            return {
                "passed": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def _build_summary(self, result: dict) -> str:
        if result["passed"]:
            return f"Client '{result['client']}' passed all harness checks."
        failed = [name for name, check in result["checks"].items() if not check["passed"]]
        return f"Client '{result['client']}' FAILED checks: {', '.join(failed)}."

    def _build_next_steps(self, result: dict) -> list[str]:
        steps = []
        for check_name, check in result["checks"].items():
            if not check["passed"]:
                if "issues" in check:
                    for issue in check["issues"]:
                        if isinstance(issue, dict) and "fix_hint" in issue:
                            steps.append(issue["fix_hint"])
                        elif isinstance(issue, str):
                            steps.append(issue)
                elif "fix_hint" in check:
                    steps.append(check["fix_hint"])
        return steps


# ------------------------------------------------------------------
# CLI interface — what the agent actually invokes
# ------------------------------------------------------------------

def main():
    harness = Harness()

    if len(sys.argv) < 2:
        usage = {
            "error": "No command specified",
            "usage": {
                "check <client_dir>": "Run all harness checks on a single client",
                "check-all <clients_dir>": "Run harness on all clients + consistency checks",
                "eval --spec <spec_file> --target <code_dir>": "Verify implementation against challenge spec",
            },
        }
        print(json.dumps(usage, indent=2))
        sys.exit(1)

    command = sys.argv[1]

    if command == "check" and len(sys.argv) >= 3:
        result = harness.check_client(Path(sys.argv[2]))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    elif command == "check-all" and len(sys.argv) >= 3:
        result = harness.check_all(Path(sys.argv[2]))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    elif command == "eval":
        args = sys.argv[2:]
        spec_path = target_path = ""
        i = 0
        while i < len(args):
            if args[i] == "--spec" and i + 1 < len(args):
                spec_path = args[i + 1]; i += 2
            elif args[i] == "--target" and i + 1 < len(args):
                target_path = args[i + 1]; i += 2
            else:
                i += 1
        if not spec_path or not target_path:
            print(json.dumps({"error": "eval requires --spec and --target"}))
            sys.exit(1)
        result = harness.eval_spec(spec_path, target_path)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
