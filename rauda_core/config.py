"""Per-client configuration loading."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ClientConfig:
    """Configuration for a client's evaluation output."""

    client_name: str
    writer_type: str  # "csv" or "airtable"
    # Airtable-specific
    airtable_base_id: str = ""
    airtable_table_name: str = ""
    airtable_api_token: str = ""
    # CSV-specific
    csv_output_path: str = "tickets_evaluated.csv"


def load_client_config(config_path: Path) -> ClientConfig:
    """Load client configuration from a YAML file.

    Environment variables can override airtable_api_token via
    AIRTABLE_API_TOKEN or <CLIENT_NAME>_AIRTABLE_API_TOKEN.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Populated ClientConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    config = ClientConfig(
        client_name=data.get("client_name", config_path.stem),
        writer_type=data.get("writer_type", "csv"),
        airtable_base_id=data.get("airtable_base_id", ""),
        airtable_table_name=data.get("airtable_table_name", ""),
        airtable_api_token=data.get("airtable_api_token", ""),
        csv_output_path=data.get("csv_output_path", "tickets_evaluated.csv"),
    )

    # Allow env var override for API token
    env_key = f"{config.client_name.upper()}_AIRTABLE_API_TOKEN"
    config.airtable_api_token = (
        os.environ.get(env_key)
        or os.environ.get("AIRTABLE_API_TOKEN")
        or config.airtable_api_token
    )

    return config
