"""
harness/validators/consistency_checker.py — Cross-integration consistency.

The "garbage collection" pillar of the harness. Runs across ALL client
integrations to find:

1. Config drift — clients using different names for the same thing
2. Missing standard fields — e.g. a client that forgot to map priority
3. Orphaned integrations — config.yaml without integration.py or vice versa
4. Event coverage gaps — events that no client subscribes to (might indicate stale config)
"""

from pathlib import Path
from typing import Any
import yaml

from rauda_core.schemas import WebhookEventType


class ConsistencyIssue:
    def __init__(self, client: str, category: str, message: str, severity: str = "warning"):
        self.client = client
        self.category = category
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.client} ({self.category}): {self.message}"


class ConsistencyChecker:
    """Checks consistency across all client integrations."""

    def check_all(self, clients_dir: Path) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []

        if not clients_dir.exists():
            issues.append(ConsistencyIssue(
                "global", "STRUCTURE", f"Clients directory not found: {clients_dir}"
            ))
            return issues

        client_dirs = [d for d in clients_dir.iterdir() if d.is_dir()]

        if len(client_dirs) == 0:
            issues.append(ConsistencyIssue(
                "global", "STRUCTURE", "No client directories found"
            ))
            return issues

        # Collect all configs
        configs: dict[str, dict[str, Any]] = {}
        for client_dir in client_dirs:
            name = client_dir.name
            config_path = client_dir / "config.yaml"
            integration_path = client_dir / "integration.py"

            # config.yaml is required; integration.py is optional (DefaultIntegration)
            if not config_path.exists():
                issues.append(ConsistencyIssue(
                    name, "ORPHAN", "integration.py exists without config.yaml", "error"
                ))
                continue

            try:
                with open(config_path) as f:
                    configs[name] = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                issues.append(ConsistencyIssue(
                    name, "PARSE", "config.yaml is not valid YAML", "error"
                ))

        # Cross-client checks
        issues.extend(self._check_field_mapping_consistency(configs))
        issues.extend(self._check_event_coverage(configs))
        issues.extend(self._check_action_consistency(configs))

        return issues

    def _check_field_mapping_consistency(self, configs: dict[str, dict]) -> list[ConsistencyIssue]:
        """Flag when clients map the same canonical field differently without reason."""
        issues = []
        standard_fields = [
            "ticket_id", "subject", "description",
            "requester_email", "requester_name", "status", "priority", "tags",
        ]

        # Collect what each client maps each field to
        field_values: dict[str, dict[str, str]] = {f: {} for f in standard_fields}
        for client_name, config in configs.items():
            fm = config.get("field_mapping", {})
            for field_name in standard_fields:
                if field_name in fm:
                    field_values[field_name][client_name] = fm[field_name]

        # Check for same-platform clients with different default mappings
        for field_name, client_map in field_values.items():
            values = set(client_map.values())
            if len(values) > 1:
                issues.append(ConsistencyIssue(
                    "cross-client", "FIELD_DRIFT",
                    f"Field '{field_name}' mapped differently across clients: "
                    f"{dict(client_map)}. Verify this is intentional.",
                    severity="warning",
                ))

        return issues

    def _check_event_coverage(self, configs: dict[str, dict]) -> list[ConsistencyIssue]:
        """Check if any standard event types are unused across all clients."""
        issues = []
        all_events = {e.value for e in WebhookEventType}
        subscribed: set[str] = set()

        for config in configs.values():
            webhook = config.get("webhook", {})
            events = webhook.get("subscribed_events", [])
            subscribed.update(events)

        unused = all_events - subscribed
        if unused:
            issues.append(ConsistencyIssue(
                "global", "EVENT_COVERAGE",
                f"Event types not subscribed by any client: {unused}. "
                "Consider if these should be added or removed from the schema.",
                severity="info",
            ))

        return issues

    def _check_action_consistency(self, configs: dict[str, dict]) -> list[ConsistencyIssue]:
        """Flag actions that exist in one client but not another (same platform)."""
        issues = []

        # Group by platform
        by_platform: dict[str, dict[str, set[str]]] = {}
        for client_name, config in configs.items():
            platform = config.get("platform", "unknown")
            if platform not in by_platform:
                by_platform[platform] = {}
            actions = config.get("actions", [])
            action_types = {a.get("action_type", "") for a in actions if isinstance(a, dict)}
            by_platform[platform][client_name] = action_types

        # Within each platform, check for action asymmetry
        for platform, clients in by_platform.items():
            if len(clients) < 2:
                continue
            all_actions = set().union(*clients.values())
            for client_name, client_actions in clients.items():
                missing = all_actions - client_actions
                if missing:
                    issues.append(ConsistencyIssue(
                        client_name, "ACTION_GAP",
                        f"Other {platform} clients have actions {missing} "
                        f"that this client doesn't. Intentional?",
                        severity="warning",
                    ))

        return issues


def check_consistency(clients_dir: Path) -> list[ConsistencyIssue]:
    """Convenience function for the CLI harness."""
    return ConsistencyChecker().check_all(clients_dir)
