"""Tests for pluggable result writers."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from rauda_core.schemas import Evaluation
from rauda_core.interfaces.writer import ResultWriter
from rauda_core.writers.csv_writer import CsvWriter
from rauda_core.writers.airtable_writer import AirtableWriter


def _sample_rows() -> list[dict[str, str]]:
    return [{"ticket": "Help me", "reply": "Sure thing"}]


def _sample_evals() -> list[Evaluation | None]:
    return [
        Evaluation(
            content_score=4,
            content_explanation="Good.",
            format_score=5,
            format_explanation="Great.",
        )
    ]


class TestCsvWriter:
    """Tests for CsvWriter."""

    def test_implements_interface(self):
        assert issubclass(CsvWriter, ResultWriter)

    def test_write_creates_csv(self, tmp_path: Path):
        output = tmp_path / "out.csv"
        writer = CsvWriter(output)
        writer.write(_sample_rows(), _sample_evals())

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            result = list(reader)

        assert len(result) == 1
        assert result[0]["content_score"] == "4"
        assert result[0]["format_explanation"] == "Great."

    def test_write_with_none_evaluation(self, tmp_path: Path):
        output = tmp_path / "out.csv"
        writer = CsvWriter(output)
        writer.write(_sample_rows(), [None])

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            result = list(reader)

        assert result[0]["content_score"] == ""


class TestAirtableWriter:
    """Tests for AirtableWriter using mocks."""

    def test_implements_interface(self):
        assert issubclass(AirtableWriter, ResultWriter)

    @patch("rauda_core.writers.airtable_writer.Api")
    def test_write_sends_records(self, mock_api_cls: MagicMock):
        mock_table = MagicMock()
        mock_api_cls.return_value.table.return_value = mock_table

        writer = AirtableWriter(
            api_token="fake_token",
            base_id="appXXX",
            table_name="Evaluations",
        )
        writer.write(_sample_rows(), _sample_evals())

        mock_api_cls.assert_called_once_with("fake_token")
        mock_api_cls.return_value.table.assert_called_once_with("appXXX", "Evaluations")
        mock_table.batch_create.assert_called_once()

        records = mock_table.batch_create.call_args[0][0]
        assert len(records) == 1
        assert records[0]["Ticket"] == "Help me"
        assert records[0]["Content Score"] == 4

    @patch("rauda_core.writers.airtable_writer.Api")
    def test_write_includes_null_for_failed_eval(self, mock_api_cls: MagicMock):
        mock_table = MagicMock()
        mock_api_cls.return_value.table.return_value = mock_table

        writer = AirtableWriter(
            api_token="fake_token",
            base_id="appXXX",
            table_name="Evaluations",
        )
        writer.write(_sample_rows(), [None])

        records = mock_table.batch_create.call_args[0][0]
        assert records[0]["Content Score"] is None
        assert records[0]["Format Score"] is None
