"""Tests for the Evaluation Pydantic model."""

import pytest
from pydantic import ValidationError

from evaluator.schemas import Evaluation


class TestEvaluationModel:
    """Tests for the Pydantic Evaluation model."""

    def test_valid_evaluation(self):
        e = Evaluation(
            content_score=4,
            content_explanation="Relevant and complete.",
            format_score=5,
            format_explanation="Clear and well-structured.",
        )
        assert e.content_score == 4
        assert e.format_score == 5

    def test_score_boundaries(self):
        for score in (1, 5):
            e = Evaluation(
                content_score=score,
                content_explanation="ok",
                format_score=score,
                format_explanation="ok",
            )
            assert e.content_score == score

    def test_score_out_of_range_low(self):
        with pytest.raises(ValidationError):
            Evaluation(
                content_score=0,
                content_explanation="ok",
                format_score=3,
                format_explanation="ok",
            )

    def test_score_out_of_range_high(self):
        with pytest.raises(ValidationError):
            Evaluation(
                content_score=6,
                content_explanation="ok",
                format_score=3,
                format_explanation="ok",
            )
