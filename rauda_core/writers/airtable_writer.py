"""Airtable result writer."""

from pyairtable import Api

from rauda_core.schemas import Evaluation
from rauda_core.interfaces.writer import ResultWriter

# Map internal field names to Airtable-friendly Title Case
_FIELD_MAP = {
    "ticket": "Ticket",
    "reply": "Reply",
    "content_score": "Content Score",
    "content_explanation": "Content Explanation",
    "format_score": "Format Score",
    "format_explanation": "Format Explanation",
}


class AirtableWriter(ResultWriter):
    """Writes evaluation results to an Airtable base."""

    def __init__(self, api_token: str, base_id: str, table_name: str) -> None:
        self.api_token = api_token
        self.base_id = base_id
        self.table_name = table_name

    def write(
        self,
        rows: list[dict[str, str]],
        evaluations: list[Evaluation | None],
    ) -> None:
        """Write evaluated results to Airtable."""
        api = Api(self.api_token)
        table = api.table(self.base_id, self.table_name)

        records = []
        for row, evaluation in zip(rows, evaluations):
            fields: dict[str, str | int | None] = {
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
            records.append(fields)

        table.batch_create(records)
