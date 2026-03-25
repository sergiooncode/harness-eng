"""Tests for CSV reading and writing."""

import csv
from pathlib import Path

import pytest

from evaluator.schemas import Evaluation
from evaluator.csv_io import read_tickets, write_results


class TestReadTickets:
    """Tests for CSV reading."""

    def test_read_valid_csv(self, tmp_path: Path):
        csv_file = tmp_path / "tickets.csv"
        csv_file.write_text("ticket,reply\nHello,Hi there\n", encoding="utf-8")
        rows = read_tickets(csv_file)
        assert len(rows) == 1
        assert rows[0]["ticket"] == "Hello"
        assert rows[0]["reply"] == "Hi there"

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_tickets(tmp_path / "nonexistent.csv")

    def test_missing_columns(self, tmp_path: Path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="ticket.*reply"):
            read_tickets(csv_file)

    def test_empty_csv_with_headers(self, tmp_path: Path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("ticket,reply\n", encoding="utf-8")
        rows = read_tickets(csv_file)
        assert rows == []


class TestWriteResults:
    """Tests for CSV writing."""

    def test_write_with_evaluations(self, tmp_path: Path):
        output = tmp_path / "out.csv"
        rows = [{"ticket": "Q", "reply": "A"}]
        evals = [
            Evaluation(
                content_score=4,
                content_explanation="Good.",
                format_score=5,
                format_explanation="Great.",
            )
        ]
        write_results(output, rows, evals)

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            result = list(reader)

        assert len(result) == 1
        assert result[0]["content_score"] == "4"
        assert result[0]["format_explanation"] == "Great."

    def test_write_with_failed_evaluation(self, tmp_path: Path):
        output = tmp_path / "out.csv"
        rows = [{"ticket": "Q", "reply": "A"}]
        evals = [None]
        write_results(output, rows, evals)

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            result = list(reader)

        assert result[0]["content_score"] == ""
        assert result[0]["format_score"] == ""

    def test_roundtrip_preserves_data(self, tmp_path: Path):
        """Write and read back to verify all columns are present."""
        output = tmp_path / "out.csv"
        rows = [{"ticket": "Help me", "reply": "Sure thing"}]
        evals = [
            Evaluation(
                content_score=3,
                content_explanation="Adequate.",
                format_score=4,
                format_explanation="Clean.",
            )
        ]
        write_results(output, rows, evals)

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames) == {
                "ticket",
                "reply",
                "content_score",
                "content_explanation",
                "format_score",
                "format_explanation",
            }
