"""Entry point for ticket reply evaluation.

Reads ticket/reply pairs from a CSV file, sends each pair to GPT-4o for
evaluation on content and format, and writes results using a pluggable writer.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from evaluator.client import evaluate_reply
from evaluator.csv_io import read_tickets
from rauda_core.config import ClientConfig, load_client_config
from rauda_core.interfaces.writer import ResultWriter
from rauda_core.writers.csv_writer import CsvWriter
from rauda_core.writers.airtable_writer import AirtableWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 10


def build_writer(config: ClientConfig) -> ResultWriter:
    """Build the appropriate writer from client config.

    Args:
        config: Client configuration.

    Returns:
        A ResultWriter instance.
    """
    if config.writer_type == "airtable":
        return AirtableWriter(
            api_token=config.airtable_api_token,
            base_id=config.airtable_base_id,
            table_name=config.airtable_table_name,
        )
    return CsvWriter(output_path=Path(config.csv_output_path))


async def process_csv(
    input_path: Path,
    writer: ResultWriter,
    max_concurrency: int = DEFAULT_CONCURRENCY,
) -> None:
    """Read tickets, evaluate them concurrently, and write results.

    Args:
        input_path: Path to the input CSV file.
        writer: ResultWriter to output evaluation results.
        max_concurrency: Maximum number of concurrent API calls.
    """
    rows = read_tickets(input_path)
    logger.info("Read %d rows from %s", len(rows), input_path)

    client = AsyncOpenAI(max_retries=0)
    semaphore = asyncio.Semaphore(max_concurrency)

    tasks = [
        evaluate_reply(client, row.get("ticket", ""), row.get("reply", ""), semaphore)
        for row in rows
    ]
    evaluations = await asyncio.gather(*tasks)

    writer.write(rows, list(evaluations))
    logger.info("Results written via %s", type(writer).__name__)


def main() -> None:
    """Entry point: load config, run evaluation pipeline."""
    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set")
        sys.exit(1)

    config_path = os.environ.get("CLIENT_CONFIG")
    if config_path:
        config = load_client_config(Path(config_path))
    else:
        config = ClientConfig(
            client_name="default",
            writer_type="airtable",
            airtable_api_token=os.environ.get("AIRTABLE_API_TOKEN", ""),
            airtable_base_id=os.environ.get("AIRTABLE_BASE_ID", ""),
            airtable_table_name=os.environ.get("AIRTABLE_TABLE_NAME", ""),
        )

    input_path = Path("resources/tickets.csv")
    max_concurrency = int(os.environ.get("MAX_CONCURRENCY", DEFAULT_CONCURRENCY))
    writer = build_writer(config)

    asyncio.run(process_csv(input_path, writer, max_concurrency))


if __name__ == "__main__":
    main()
