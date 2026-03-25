"""Tests for the OpenAI client wrapper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from evaluator.schemas import Evaluation
from evaluator.client import evaluate_reply


class TestEvaluateReply:
    """Tests for the evaluate_reply function with mocked API."""

    def setup_method(self):
        self.semaphore = asyncio.Semaphore(1)

    def _mock_evaluation(self) -> Evaluation:
        return Evaluation(
            content_score=4,
            content_explanation="Relevant response.",
            format_score=5,
            format_explanation="Well-written.",
        )

    def test_successful_evaluation(self):
        client = AsyncMock()
        response = MagicMock()
        response.output_parsed = self._mock_evaluation()
        client.responses.parse = AsyncMock(return_value=response)

        result = asyncio.run(evaluate_reply(client, "ticket text", "reply text", self.semaphore))
        assert result is not None
        assert result.content_score == 4
        assert result.format_score == 5

    def test_empty_ticket_returns_none(self):
        client = AsyncMock()
        result = asyncio.run(evaluate_reply(client, "", "reply text", self.semaphore))
        assert result is None

    def test_empty_reply_returns_none(self):
        client = AsyncMock()
        result = asyncio.run(evaluate_reply(client, "ticket text", "  ", self.semaphore))
        assert result is None

    def test_retryable_error_retries_then_fails(self):
        from openai import RateLimitError

        client = AsyncMock()
        client.responses.parse = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )
        )

        with patch("evaluator.client.BASE_DELAY", 0.01):
            result = asyncio.run(
                evaluate_reply(client, "ticket text", "reply text", self.semaphore)
            )
        assert result is None
        assert client.responses.parse.call_count == 3  # MAX_RETRIES

    def test_auth_error_fails_immediately(self):
        from openai import AuthenticationError

        client = AsyncMock()
        client.responses.parse = AsyncMock(
            side_effect=AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401, headers={}),
                body=None,
            )
        )

        result = asyncio.run(
            evaluate_reply(client, "ticket text", "reply text", self.semaphore)
        )
        assert result is None
        assert client.responses.parse.call_count == 1  # no retries
