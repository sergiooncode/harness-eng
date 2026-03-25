"""
harness/validators/schema_validator.py — Deterministic config validation.

Validates that a client's config.yaml is well-formed and complete.
This is the first line of defense in the harness — runs before any code.
"""

import yaml
from pathlib import Path
from dataclasses import fields
from typing import get_type_hints

from rauda_core.schemas import (
    ClientConfig, WebhookConfig, InfoRepository, ClientAction,
    EvalConfig, FieldMapping, SupportPlatform, WebhookEventType, ActionType,
)


class ValidationError:
    def __init__(self, path: str, message: str, severity: str = "error"):
        self.path = path
        self.message = message
        self.severity = severity  # "error" or "warning"

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.path}: {self.message}"


class ConfigValidator:
    """Validates a config.yaml against the ClientConfig schema."""

    REQUIRED_TOP_LEVEL = {"client_name", "client_slug", "platform", "webhook", "field_mapping"}
    VALID_PLATFORMS = {p.value for p in SupportPlatform}
    VALID_EVENT_TYPES = {e.value for e in WebhookEventType}
    VALID_ACTION_TYPES = {a.value for a in ActionType}
    VALID_AUTH_METHODS = {"bearer_token", "hmac_signature", "api_key"}
    VALID_REPO_TYPES = {"api", "database", "knowledge_base", "airtable"}

    def validate_file(self, config_path: Path) -> list[ValidationError]:
        """Validate a config.yaml file. Returns list of errors (empty = valid)."""
        errors: list[ValidationError] = []

        if not config_path.exists():
            errors.append(ValidationError("config.yaml", "File not found"))
            return errors

        try:
            with open(config_path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            errors.append(ValidationError("config.yaml", f"Invalid YAML: {e}"))
            return errors

        if not isinstance(raw, dict):
            errors.append(ValidationError("config.yaml", "Root must be a mapping"))
            return errors

        errors.extend(self._validate_top_level(raw))
        errors.extend(self._validate_webhook(raw.get("webhook", {})))
        errors.extend(self._validate_field_mapping(raw.get("field_mapping", {})))
        errors.extend(self._validate_info_repositories(raw.get("info_repositories", [])))
        errors.extend(self._validate_actions(raw.get("actions", [])))
        errors.extend(self._validate_eval(raw.get("eval", {})))

        return errors

    def _validate_top_level(self, raw: dict) -> list[ValidationError]:
        errors = []
        missing = self.REQUIRED_TOP_LEVEL - set(raw.keys())
        for key in missing:
            errors.append(ValidationError(key, "Required field missing"))

        if "platform" in raw and raw["platform"] not in self.VALID_PLATFORMS:
            errors.append(ValidationError(
                "platform",
                f"Must be one of {self.VALID_PLATFORMS}, got '{raw['platform']}'"
            ))

        if "client_slug" in raw:
            slug = raw["client_slug"]
            if not isinstance(slug, str):
                errors.append(ValidationError("client_slug", "Must be a string"))
            elif slug != slug.lower():
                errors.append(ValidationError("client_slug", "Must be lowercase"))
            elif not slug.replace("_", "").replace("-", "").isalnum():
                errors.append(ValidationError("client_slug", "Must be alphanumeric with _ or -"))

        return errors

    def _validate_webhook(self, webhook: dict) -> list[ValidationError]:
        errors = []
        if not isinstance(webhook, dict):
            errors.append(ValidationError("webhook", "Must be a mapping"))
            return errors

        if "subscribed_events" not in webhook:
            errors.append(ValidationError("webhook.subscribed_events", "Required"))
        elif not isinstance(webhook["subscribed_events"], list):
            errors.append(ValidationError("webhook.subscribed_events", "Must be a list"))
        else:
            for i, evt in enumerate(webhook["subscribed_events"]):
                if evt not in self.VALID_EVENT_TYPES:
                    errors.append(ValidationError(
                        f"webhook.subscribed_events[{i}]",
                        f"Invalid event type '{evt}'. Valid: {self.VALID_EVENT_TYPES}"
                    ))

        if "auth_method" in webhook and webhook["auth_method"] not in self.VALID_AUTH_METHODS:
            errors.append(ValidationError(
                "webhook.auth_method",
                f"Must be one of {self.VALID_AUTH_METHODS}"
            ))

        if "auth_secret_env_var" not in webhook:
            errors.append(ValidationError("webhook.auth_secret_env_var", "Required"))

        return errors

    def _validate_field_mapping(self, fm: dict) -> list[ValidationError]:
        errors = []
        if not isinstance(fm, dict):
            errors.append(ValidationError("field_mapping", "Must be a mapping"))
        # field_mapping has sensible defaults, so mostly just type-check
        if "custom_fields" in fm and not isinstance(fm.get("custom_fields"), dict):
            errors.append(ValidationError("field_mapping.custom_fields", "Must be a mapping"))
        return errors

    def _validate_info_repositories(self, repos: list) -> list[ValidationError]:
        errors = []
        if not isinstance(repos, list):
            errors.append(ValidationError("info_repositories", "Must be a list"))
            return errors
        for i, repo in enumerate(repos):
            prefix = f"info_repositories[{i}]"
            if not isinstance(repo, dict):
                errors.append(ValidationError(prefix, "Must be a mapping"))
                continue
            for req in ("name", "type", "description"):
                if req not in repo:
                    errors.append(ValidationError(f"{prefix}.{req}", "Required"))
            if "type" in repo and repo["type"] not in self.VALID_REPO_TYPES:
                errors.append(ValidationError(
                    f"{prefix}.type",
                    f"Must be one of {self.VALID_REPO_TYPES}"
                ))
        return errors

    def _validate_actions(self, actions: list) -> list[ValidationError]:
        errors = []
        if not isinstance(actions, list):
            errors.append(ValidationError("actions", "Must be a list"))
            return errors
        for i, action in enumerate(actions):
            prefix = f"actions[{i}]"
            if not isinstance(action, dict):
                errors.append(ValidationError(prefix, "Must be a mapping"))
                continue
            for req in ("name", "action_type", "description"):
                if req not in action:
                    errors.append(ValidationError(f"{prefix}.{req}", "Required"))
            if "action_type" in action and action["action_type"] not in self.VALID_ACTION_TYPES:
                errors.append(ValidationError(
                    f"{prefix}.action_type",
                    f"Must be one of {self.VALID_ACTION_TYPES}"
                ))
        return errors

    def _validate_eval(self, eval_config: dict) -> list[ValidationError]:
        errors = []
        if not isinstance(eval_config, dict):
            return errors  # eval is optional
        if "quality_threshold" in eval_config:
            qt = eval_config["quality_threshold"]
            if not isinstance(qt, (int, float)) or not (0.0 <= qt <= 1.0):
                errors.append(ValidationError(
                    "eval.quality_threshold", "Must be a number between 0.0 and 1.0"
                ))
        return errors


def validate_config(config_path: Path) -> list[ValidationError]:
    """Convenience function for the CLI harness."""
    return ConfigValidator().validate_file(config_path)
