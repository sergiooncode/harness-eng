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

    def validate(self, path: Path) -> dict:
        """Common interface: validate a file and return structured result."""
        errors = self.validate_file(path)
        return {
            "passed": not any(e.severity == "error" for e in errors),
            "file": str(path),
            "issues": [
                {"field": e.path, "message": e.message, "severity": e.severity}
                for e in errors
            ],
        }

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


class WorkflowValidator:
    """Validates a workflow.yaml against structural rules."""

    VALID_STEP_TYPES = {"llm", "code"}

    def validate(self, path: Path) -> dict:
        """Common interface: validate a file and return structured result."""
        errors = self.validate_file(path)
        return {
            "passed": not any(e.severity == "error" for e in errors),
            "file": str(path),
            "issues": [
                {"field": e.path, "message": e.message, "severity": e.severity}
                for e in errors
            ],
        }

    def validate_file(self, workflow_path: Path) -> list[ValidationError]:
        """Validate a workflow.yaml file. Returns list of errors (empty = valid)."""
        errors: list[ValidationError] = []

        if not workflow_path.exists():
            errors.append(ValidationError("workflow.yaml", "File not found"))
            return errors

        try:
            with open(workflow_path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            errors.append(ValidationError("workflow.yaml", f"Invalid YAML: {e}"))
            return errors

        if not isinstance(raw, dict):
            errors.append(ValidationError("workflow.yaml", "Root must be a mapping"))
            return errors

        if "name" not in raw:
            errors.append(ValidationError("name", "Required field missing"))

        steps = raw.get("steps", [])
        if not isinstance(steps, list):
            errors.append(ValidationError("steps", "Must be a list"))
            return errors

        if not steps:
            errors.append(ValidationError("steps", "Workflow must have at least one step"))
            return errors

        errors.extend(self._validate_steps(steps))
        return errors

    def _validate_steps(self, steps: list) -> list[ValidationError]:
        errors: list[ValidationError] = []
        output_keys_seen: set[str] = set()
        available_keys: set[str] = set()

        for i, step in enumerate(steps):
            prefix = f"steps[{i}]"
            if not isinstance(step, dict):
                errors.append(ValidationError(prefix, "Must be a mapping"))
                continue

            # Required fields
            for req in ("name", "type", "output_key"):
                if req not in step:
                    errors.append(ValidationError(f"{prefix}.{req}", "Required"))

            # Valid step type
            step_type = step.get("type")
            if step_type and step_type not in self.VALID_STEP_TYPES:
                errors.append(ValidationError(
                    f"{prefix}.type",
                    f"Must be one of {sorted(self.VALID_STEP_TYPES)}, got '{step_type}'"
                ))

            # Unique output keys
            output_key = step.get("output_key")
            if output_key:
                if output_key in output_keys_seen:
                    errors.append(ValidationError(
                        f"{prefix}.output_key",
                        f"Duplicate output_key '{output_key}' — must be unique across steps"
                    ))
                output_keys_seen.add(output_key)

            # LLM steps must have a model
            if step_type == "llm":
                if not step.get("model"):
                    errors.append(ValidationError(
                        f"{prefix}.model", "LLM steps must specify a model"
                    ))
                if not step.get("prompt_template"):
                    errors.append(ValidationError(
                        f"{prefix}.prompt_template", "LLM steps must specify a prompt_template"
                    ))

            # Code steps must have a function
            if step_type == "code":
                if not step.get("function"):
                    errors.append(ValidationError(
                        f"{prefix}.function", "Code steps must specify a function"
                    ))
                # Check input_keys are satisfied by prior steps' output_keys.
                # Keys may also come from initial context (runtime), so warn rather than error.
                for key in step.get("input_keys", []):
                    if key not in available_keys:
                        errors.append(ValidationError(
                            f"{prefix}.input_keys",
                            f"Input key '{key}' not produced by any prior step. "
                            f"Available: {sorted(available_keys) if available_keys else 'none'}. "
                            f"OK if provided in initial context.",
                            severity="warning",
                        ))

            if output_key:
                available_keys.add(output_key)

        return errors


def validate_config(config_path: Path) -> list[ValidationError]:
    """Convenience function for the CLI harness."""
    return ConfigValidator().validate_file(config_path)
