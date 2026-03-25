"""CSV reading and writing utilities.

read_tickets remains here as it's input-side logic.
write_results is kept for backward compatibility but delegates to CsvWriter.
"""

import csv
from pathlib import Path

from rauda_core.schemas import Evaluation
from rauda_core.writers.csv_writer import CsvWriter


def read_tickets(input_path: Path) -> list[dict[str, str]]:
    """Read ticket/reply pairs from a CSV file.

    Args:
        input_path: Path to the input CSV file.

    Returns:
        List of dicts with 'ticket' and 'reply' keys.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If required columns are missing.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not {"ticket", "reply"}.issubset(reader.fieldnames):
            raise ValueError("CSV must contain 'ticket' and 'reply' columns")
        return list(reader)


def write_results(
    output_path: Path,
    rows: list[dict[str, str]],
    evaluations: list[Evaluation | None],
) -> None:
    """Write evaluated results to a CSV file.

    Delegates to CsvWriter for backward compatibility.
    """
    CsvWriter(output_path).write(rows, evaluations)
