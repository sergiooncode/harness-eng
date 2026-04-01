"""Batch evaluation of ticket replies using OpenAI Batch API.

Uploads all ticket/reply pairs as a JSONL batch to the OpenAI Batch API
for cost-efficient processing at scale (50% cost reduction).
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema

from evaluator.csv_io import read_tickets, write_results
from evaluator.schemas import Evaluation, SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 30
EVALUATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "Evaluation",
        "strict": True,
        "schema": to_strict_json_schema(Evaluation),
    },
}


def build_jsonl(rows: list[dict[str, str]]) -> str:
    """Build JSONL content for the batch request.

    Args:
        rows: Ticket/reply pairs from the CSV.

    Returns:
        JSONL string with one request per line.
    """
    lines = []
    for i, row in enumerate(rows):
        ticket = row.get("ticket", "")
        reply = row.get("reply", "")
        request = {
            "custom_id": str(i),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Ticket: {ticket}\n\nReply: {reply}"},
                ],
                "response_format": EVALUATION_SCHEMA,
            },
        }
        lines.append(json.dumps(request))
    return "\n".join(lines)


def parse_results(
    result_content: bytes, row_count: int
) -> list[Evaluation | None]:
    """Parse batch API results back into Evaluation objects.

    Args:
        result_content: Raw bytes of the output JSONL file.
        row_count: Total number of input rows (for ordering).

    Returns:
        List of Evaluations aligned by original row index.
    """
    evaluations: list[Evaluation | None] = [None] * row_count

    for line in result_content.decode("utf-8").strip().split("\n"):
        result = json.loads(line)
        idx = int(result["custom_id"])

        if result.get("error"):
            logger.error("Row %d failed: %s", idx, result["error"])
            continue

        try:
            content = result["response"]["body"]["choices"][0]["message"]["content"]
            evaluations[idx] = Evaluation.model_validate_json(content)
        except Exception as e:
            logger.error("Row %d parse error: %s", idx, e)

    return evaluations


def main() -> None:
    """Entry point: upload batch, poll, write results."""
    parser = argparse.ArgumentParser(description="Batch evaluate ticket replies via OpenAI Batch API")
    parser.add_argument("input", nargs="?", default="resources/tickets.csv", help="Input CSV path")
    parser.add_argument("-o", "--output", default="tickets_evaluated.csv", help="Output CSV path")
    args = parser.parse_args()

    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set")
        sys.exit(1)

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = read_tickets(input_path)
    logger.info("Read %d rows from %s", len(rows), input_path)

    client = OpenAI()

    # Build and upload JSONL
    jsonl_content = build_jsonl(rows)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(jsonl_content)
        jsonl_path = f.name

    batch_file = client.files.create(
        file=open(jsonl_path, "rb"),
        purpose="batch",
    )
    logger.info("Uploaded batch file: %s", batch_file.id)
    Path(jsonl_path).unlink()

    # Create batch
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    logger.info("Created batch: %s", batch.id)

    # Poll for completion
    while True:
        batch = client.batches.retrieve(batch.id)
        status = batch.status
        logger.info("Batch status: %s", status)

        if status in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(POLL_INTERVAL)

    if status != "completed":
        logger.error("Batch ended with status: %s", status)
        sys.exit(1)

    # Retrieve and parse results
    result_content = client.files.content(batch.output_file_id).content
    evaluations = parse_results(result_content, len(rows))

    failed = sum(1 for e in evaluations if e is None)
    if failed:
        logger.warning("%d rows failed evaluation", failed)

    write_results(output_path, rows, evaluations)
    logger.info("Wrote results to %s", output_path)


if __name__ == "__main__":
    main()
