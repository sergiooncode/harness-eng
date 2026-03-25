"""Config-driven integration for standard clients.

Most clients do not need custom Python code. This class implements all
BaseIntegration methods using only the data in config.yaml:

  - validate_webhook: dispatches on auth_method (hmac_signature, bearer_token, api_key)
  - parse_webhook: applies field_mapping to build a CanonicalTicket
  - enrich_context: records which info_repositories would be called
  - execute_action: looks up the action config and routes accordingly

To onboard a new client, create clients/<slug>/config.yaml and you're done.
If a client needs truly custom behaviour, subclass DefaultIntegration and
override only the method that differs.
"""

import hashlib
import hmac
import os
from typing import Any

from rauda_core.interfaces.integration import (
    BaseIntegration,
    CanonicalTicket,
    EnrichedContext,
    AgentDecision,
    ActionResult,
)
from rauda_core.schemas import WebhookEventType


class DefaultIntegration(BaseIntegration):
    """Config-driven integration that covers the common case without code."""

    # ------------------------------------------------------------------
    # Webhook authentication
    # ------------------------------------------------------------------

    def validate_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Authenticate the webhook based on the configured auth_method."""
        method = self.config.webhook.auth_method
        secret = os.environ.get(self.config.webhook.auth_secret_env_var, "")
        if not secret:
            return False

        if method == "hmac_signature":
            return self._validate_hmac(headers, body, secret)
        elif method == "bearer_token":
            return self._validate_bearer(headers, secret)
        elif method == "api_key":
            return self._validate_api_key(headers, secret)

        return False

    def _validate_hmac(self, headers: dict[str, str], body: bytes, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        actual = headers.get("X-Zendesk-Webhook-Signature", "")
        return hmac.compare_digest(expected, actual)

    def _validate_bearer(self, headers: dict[str, str], secret: str) -> bool:
        return headers.get("Authorization", "") == f"Bearer {secret}"

    def _validate_api_key(self, headers: dict[str, str], secret: str) -> bool:
        return headers.get("X-API-Key", "") == secret

    # ------------------------------------------------------------------
    # Webhook parsing
    # ------------------------------------------------------------------

    def parse_webhook(self, payload: dict[str, Any]) -> tuple[WebhookEventType, CanonicalTicket]:
        """Parse a raw webhook payload using field_mapping from config."""
        fm = self.config.field_mapping

        event_type_raw = payload.get("event", "ticket_created")
        event_type = WebhookEventType(event_type_raw)

        ticket_data = payload.get("ticket", payload)

        ticket = CanonicalTicket(
            ticket_id=str(_extract_field(ticket_data, fm.ticket_id)),
            subject=_extract_field(ticket_data, fm.subject, ""),
            description=_extract_field(ticket_data, fm.description, ""),
            requester_email=_extract_field(ticket_data, fm.requester_email, ""),
            requester_name=_extract_field(ticket_data, fm.requester_name, ""),
            status=_extract_field(ticket_data, fm.status, "new"),
            priority=_extract_field(ticket_data, fm.priority, "normal"),
            tags=_extract_field(ticket_data, fm.tags, []),
            custom_fields={
                canonical: _extract_field(ticket_data, source_path, "")
                for canonical, source_path in fm.custom_fields.items()
            },
            raw_payload=payload,
        )
        return event_type, ticket

    # ------------------------------------------------------------------
    # Context enrichment
    # ------------------------------------------------------------------

    def enrich_context(self, ticket: CanonicalTicket) -> EnrichedContext:
        """Build enriched context from info_repositories in config.

        In production each repository entry would trigger an API call.
        The config tells us *what* to call; this method handles *how*.
        """
        repository_data: dict[str, Any] = {}
        for repo in self.config.info_repositories:
            repository_data[repo.name] = {
                "source": repo.name,
                "type": repo.type,
                "base_url": repo.base_url,
                "status": "stub — would fetch from " + repo.base_url,
            }
        return EnrichedContext(ticket=ticket, repository_data=repository_data)

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def execute_action(self, decision: AgentDecision, ticket: CanonicalTicket) -> ActionResult:
        """Execute an action by looking up its config entry."""
        action_config = None
        for a in self.config.actions:
            if a.action_type == decision.action_type:
                action_config = a
                break

        if action_config is None:
            return ActionResult(
                success=False,
                action_type=decision.action_type,
                message=f"No action configured for {decision.action_type.value}",
            )

        if action_config.requires_confirmation and decision.confidence < 0.9:
            return ActionResult(
                success=False,
                action_type=decision.action_type,
                message="Action requires confirmation and confidence is below 0.9",
            )

        endpoint = action_config.endpoint.format(
            ticket_id=ticket.ticket_id,
            **ticket.custom_fields,
        ) if action_config.endpoint else ""

        return ActionResult(
            success=True,
            action_type=decision.action_type,
            message=f"Stub — would call {endpoint}" if endpoint else "Action executed",
            details={"reply_text": decision.reply_text},
        )


def _extract_field(data: dict, dotted_path: str, default: Any = None) -> Any:
    """Navigate a dotted path like 'requester.email' through nested dicts."""
    parts = dotted_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            return default
    return current
