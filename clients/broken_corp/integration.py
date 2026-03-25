"""Deliberately broken integration for harness testing."""

import requests  # FORBIDDEN in parse_webhook
from typing import Any

from rauda_core.interfaces.integration import (
    BaseIntegration,
    CanonicalTicket,
    EnrichedContext,
    AgentDecision,
    ActionResult,
)
from rauda_core.schemas import WebhookEventType, ActionType


class BrokenCorpIntegration(BaseIntegration):

    # Missing: validate_webhook (STRUCT-003)

    def parse_webhook(self, payload: dict[str, Any]) -> tuple[WebhookEventType, CanonicalTicket]:
        import httpx  # PURE-001: HTTP library in parse_webhook
        return WebhookEventType.TICKET_CREATED, CanonicalTicket(
            ticket_id="1", subject="", description="",
            requester_email="", requester_name="", status="", priority="",
        )

    def enrich_context(self, ticket: CanonicalTicket) -> EnrichedContext:
        return EnrichedContext(ticket=ticket)

    def execute_action(self, decision: AgentDecision, ticket: CanonicalTicket) -> ActionResult:
        return ActionResult(success=True, action_type=decision.action_type, message="ok")

    def handle_webhook(self, headers, body, payload):  # STRUCT-004: must NOT override
        pass


class ExtraIntegration(BaseIntegration):  # STRUCT-002: multiple subclasses
    def validate_webhook(self, headers, body): return True
    def parse_webhook(self, payload): pass
    def enrich_context(self, ticket): pass
    def execute_action(self, decision, ticket): pass
