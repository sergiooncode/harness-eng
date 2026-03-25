"""Tests for client configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from rauda_core.config import ClientConfig, load_client_config


class TestLoadClientConfig:
    """Tests for YAML config loading."""

    def test_load_csv_config(self, tmp_path: Path):
        cfg = tmp_path / "client.yaml"
        cfg.write_text(
            "client_name: acme\nwriter_type: csv\ncsv_output_path: out.csv\n"
        )
        config = load_client_config(cfg)
        assert config.client_name == "acme"
        assert config.writer_type == "csv"
        assert config.csv_output_path == "out.csv"

    def test_load_airtable_config(self, tmp_path: Path):
        cfg = tmp_path / "client.yaml"
        cfg.write_text(
            "client_name: globex\n"
            "writer_type: airtable\n"
            "airtable_base_id: appXXX\n"
            "airtable_table_name: Evals\n"
            "airtable_api_token: pat123\n"
        )
        config = load_client_config(cfg)
        assert config.writer_type == "airtable"
        assert config.airtable_base_id == "appXXX"
        assert config.airtable_api_token == "pat123"

    def test_env_var_overrides_token(self, tmp_path: Path):
        cfg = tmp_path / "client.yaml"
        cfg.write_text(
            "client_name: acme\nwriter_type: airtable\nairtable_api_token: from_yaml\n"
        )
        with patch.dict(os.environ, {"ACME_AIRTABLE_API_TOKEN": "from_env"}):
            config = load_client_config(cfg)
        assert config.airtable_api_token == "from_env"

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_client_config(tmp_path / "missing.yaml")
