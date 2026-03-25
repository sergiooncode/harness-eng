"""CSV result writer."""

import csv
from pathlib import Path

from rauda_core.schemas import Evaluation
from rauda_core.interfaces.writer import ResultWriter


class CsvWriter(ResultWriter):
    """Writes evaluation results to a CSV file."""

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def write(
        self,
        rows: list[dict[str, str]],
        evaluations: list[Evaluation | None],
    ) -> None:
        """Write evaluated results to a CSV file."""
        fieldnames = [
            "ticket",
            "reply",
            "content_score",
            "content_explanation",
            "format_score",
            "format_explanation",
        ]
        with open(self.output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row, evaluation in zip(rows, evaluations):
                out = {"ticket": row.get("ticket", ""), "reply": row.get("reply", "")}
                if evaluation:
                    out.update(evaluation.model_dump())
                else:
                    out.update(
                        content_score="",
                        content_explanation="",
                        format_score="",
                        format_explanation="",
                    )
                writer.writerow(out)
