"""
harness/registry.py — Integration discovery and registration.

Auto-discovers client integrations from the clients/ directory,
validates them through the harness, and registers them for use.
"""

import importlib.util
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from harness.schema import (
    ClientConfig, WebhookConfig, FieldMapping, InfoRepository,
    ClientAction, EvalConfig, SupportPlatform, WebhookEventType, ActionType,
)
from harness.integrations.base import BaseIntegration
from harness.validators.schema_validator import validate_config
from harness.validators.structural_linter import lint_integration


@dataclass
class RegistrationResult:
    client_slug: str
    success: bool
    integration: Optional[BaseIntegration] = None
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _load_config_from_yaml(config_path: Path) -> ClientConfig:
    """Parse config.yaml into a typed ClientConfig dataclass."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    webhook = WebhookConfig(
        subscribed_events=[WebhookEventType(e) for e in raw["webhook"]["subscribed_events"]],
        auth_method=raw["webhook"]["auth_method"],
        auth_secret_env_var=raw["webhook"]["auth_secret_env_var"],
    )

    fm_raw = raw.get("field_mapping", {})
    field_mapping = FieldMapping(
        ticket_id=fm_raw.get("ticket_id", "id"),
        subject=fm_raw.get("subject", "subject"),
        description=fm_raw.get("description", "description"),
        requester_email=fm_raw.get("requester_email", "requester.email"),
        requester_name=fm_raw.get("requester_name", "requester.name"),
        status=fm_raw.get("status", "status"),
        priority=fm_raw.get("priority", "priority"),
        tags=fm_raw.get("tags", "tags"),
        custom_fields=fm_raw.get("custom_fields", {}),
    )

    info_repos = [
        InfoRepository(**repo) for repo in raw.get("info_repositories", [])
    ]
    actions = [
        ClientAction(
            name=a["name"],
            action_type=ActionType(a["action_type"]),
            description=a["description"],
            endpoint=a.get("endpoint", ""),
            requires_confirmation=a.get("requires_confirmation", False),
        )
        for a in raw.get("actions", [])
    ]

    eval_raw = raw.get("eval", {})
    eval_config = EvalConfig(**eval_raw) if eval_raw else EvalConfig()

    return ClientConfig(
        client_name=raw["client_name"],
        client_slug=raw["client_slug"],
        platform=SupportPlatform(raw["platform"]),
        webhook=webhook,
        field_mapping=field_mapping,
        info_repositories=info_repos,
        actions=actions,
        eval=eval_config,
    )


def _load_integration_class(integration_path: Path) -> type:
    """Dynamically load integration.py and find the BaseIntegration subclass."""
    spec = importlib.util.spec_from_file_location("client_integration", integration_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["client_integration"] = module
    spec.loader.exec_module(module)

    # Find the BaseIntegration subclass
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseIntegration)
            and attr is not BaseIntegration
        ):
            return attr

    raise ValueError(f"No BaseIntegration subclass found in {integration_path}")


def register_client(client_dir: Path) -> RegistrationResult:
    """Register a single client integration through the full harness pipeline.
    
    Pipeline:
    1. Validate config.yaml schema
    2. Lint integration.py structure
    3. Load and instantiate the integration
    """
    slug = client_dir.name
    config_path = client_dir / "config.yaml"
    integration_path = client_dir / "integration.py"

    # Step 1: Config validation
    config_errors = validate_config(config_path)
    if any(e.severity == "error" for e in config_errors):
        return RegistrationResult(
            client_slug=slug,
            success=False,
            errors=[repr(e) for e in config_errors],
        )

    # Step 2: Structural linting
    if integration_path.exists():
        lint_issues = lint_integration(integration_path)
        if any(i.severity == "error" for i in lint_issues):
            return RegistrationResult(
                client_slug=slug,
                success=False,
                errors=[repr(i) for i in lint_issues],
            )

    # Step 3: Load config and integration
    try:
        config = _load_config_from_yaml(config_path)
        integration_cls = _load_integration_class(integration_path)
        integration = integration_cls(config)
    except Exception as e:
        return RegistrationResult(
            client_slug=slug,
            success=False,
            errors=[f"Failed to load integration: {e}"],
        )

    return RegistrationResult(
        client_slug=slug,
        success=True,
        integration=integration,
    )


def discover_and_register(clients_dir: Path) -> dict[str, RegistrationResult]:
    """Discover all clients and register them through the harness."""
    results = {}
    if not clients_dir.exists():
        return results

    for client_dir in sorted(clients_dir.iterdir()):
        if client_dir.is_dir() and not client_dir.name.startswith("."):
            results[client_dir.name] = register_client(client_dir)

    return results
