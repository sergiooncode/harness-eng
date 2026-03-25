"""OpenAI client wrapper for evaluating ticket replies."""

import asyncio
import logging

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, RateLimitError

from evaluator.schemas import Evaluation, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0
RETRYABLE_ERRORS = (RateLimitError, APITimeoutError)


async def evaluate_reply(
    client: AsyncOpenAI,
    ticket: str,
    reply: str,
    semaphore: asyncio.Semaphore,
) -> Evaluation | None:
    """Evaluate a single ticket/reply pair using GPT-4o.

    Retries on transient API errors with exponential backoff.

    Args:
        client: AsyncOpenAI client instance.
        ticket: Customer support ticket text.
        reply: AI-generated reply text.
        semaphore: Semaphore to limit concurrent API calls.

    Returns:
        Evaluation result, or None if all retries failed.
    """
    if not ticket.strip() or not reply.strip():
        logger.warning("Skipping row with empty ticket or reply")
        return None

    user_prompt = f"Ticket: {ticket}\n\nReply: {reply}"

    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.responses.parse(
                    model="gpt-4o",
                    instructions=SYSTEM_PROMPT,
                    input=user_prompt,
                    text_format=Evaluation,
                )
                return response.output_parsed
            except RETRYABLE_ERRORS as e:
                if attempt == MAX_RETRIES:
                    logger.error("Failed after %d retries: %s", MAX_RETRIES, e)
                    return None
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.warning("Attempt %d failed (%s), retrying in %.1fs", attempt, e, delay)
                await asyncio.sleep(delay)
            except APIStatusError as e:
                logger.error("API error (status %d): %s", e.status_code, e.message)
                return None
            except Exception as e:
                logger.error("Unexpected error: %s", e)
                return None

    return None  # unreachable, but satisfies type checker
