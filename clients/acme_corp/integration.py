"""
Acme Corp Zendesk integration.

This integration was created by the Engagement team for Acme Corp.
It handles Zendesk webhooks for customer support tickets.
"""

import hashlib
import hmac
import json
import os
from typing import Any

from harness.integrations.base import (
    BaseIntegration,
    CanonicalTicket,
    EnrichedContext,
    AgentDecision,
    ActionResult,
)
from harness.schema import WebhookEventType, ActionType


class AcmeCorpIntegration(BaseIntegration):

    def validate_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        secret = os.environ.get(self.config.webhook.auth_secret_env_var, "")
        if not secret:
            return False
        expected_sig = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        actual_sig = headers.get("X-Zendesk-Webhook-Signature", "")
        return hmac.compare_digest(expected_sig, actual_sig)

    def parse_webhook(self, payload: dict[str, Any]) -> tuple[WebhookEventType, CanonicalTicket]:
        fm = self.config.field_mapping

        event_type_raw = payload.get("event", "ticket_created")
        event_type = WebhookEventType(event_type_raw)

        ticket_data = payload.get("ticket", payload)

        # Apply field mapping to extract canonical fields
        ticket = CanonicalTicket(
            ticket_id=str(self._extract_field(ticket_data, fm.ticket_id)),
            subject=self._extract_field(ticket_data, fm.subject, ""),
            description=self._extract_field(ticket_data, fm.description, ""),
            requester_email=self._extract_field(ticket_data, fm.requester_email, ""),
            requester_name=self._extract_field(ticket_data, fm.requester_name, ""),
            status=self._extract_field(ticket_data, fm.status, "new"),
            priority=self._extract_field(ticket_data, fm.priority, "normal"),
            tags=self._extract_field(ticket_data, fm.tags, []),
            custom_fields={
                canonical: self._extract_field(ticket_data, source_path, "")
                for canonical, source_path in fm.custom_fields.items()
            },
            raw_payload=payload,
        )
        return event_type, ticket

    def enrich_context(self, ticket: CanonicalTicket) -> EnrichedContext:
        repository_data = {}

        for repo in self.config.info_repositories:
            if repo.name == "Order History API":
                # In production: call repo.base_url with ticket.requester_email
                repository_data["order_history"] = {
                    "source": repo.name,
                    "status": "stub — would fetch from " + repo.base_url,
                }
            elif repo.name == "Product Knowledge Base":
                repository_data["knowledge_base"] = {
                    "source": repo.name,
                    "status": "stub — would search " + repo.base_url,
                }

        return EnrichedContext(ticket=ticket, repository_data=repository_data)

    def execute_action(self, decision: AgentDecision, ticket: CanonicalTicket) -> ActionResult:
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

        # In production: make HTTP call to action_config.endpoint
        return ActionResult(
            success=True,
            action_type=decision.action_type,
            message=f"Stub — would call {action_config.endpoint}",
            details={"reply_text": decision.reply_text},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
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
