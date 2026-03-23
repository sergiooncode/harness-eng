"""
harness/integrations/base.py — Abstract base for all client integrations.

Every client's integration.py must subclass BaseIntegration and implement
all abstract methods. The harness verifies this structurally.

The pipeline is: parse_webhook → enrich_context → decide_action → execute_action
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from harness.schema import ClientConfig, WebhookEventType, ActionType


# ---------------------------------------------------------------------------
# Canonical data types that flow through the pipeline
# ---------------------------------------------------------------------------

@dataclass
class CanonicalTicket:
    """Platform-agnostic ticket representation.
    
    Integrations parse platform-specific payloads into this canonical form.
    Everything downstream in Rauda Core works with CanonicalTicket, never
    with raw Zendesk/Intercom payloads.
    """
    ticket_id: str
    subject: str
    description: str
    requester_email: str
    requester_name: str
    status: str
    priority: str
    tags: list[str] = field(default_factory=list)
    custom_fields: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichedContext:
    """Ticket + additional context fetched from info repositories."""
    ticket: CanonicalTicket
    repository_data: dict[str, Any] = field(default_factory=dict)
    # e.g. {"order_history": [...], "knowledge_base_articles": [...]}


@dataclass
class AgentDecision:
    """What the AI agent decided to do."""
    action_type: ActionType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    reply_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Outcome of executing an action."""
    success: bool
    action_type: ActionType
    message: str
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base — the contract
# ---------------------------------------------------------------------------

class BaseIntegration(ABC):
    """Abstract base class for all client integrations.
    
    Subclasses MUST implement all @abstractmethod methods.
    The harness structurally verifies this at registration time.
    """

    def __init__(self, config: ClientConfig):
        self.config = config

    @abstractmethod
    def validate_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify that the incoming webhook is authentic.
        
        Args:
            headers: HTTP headers from the webhook request
            body: Raw request body bytes
            
        Returns:
            True if the webhook signature/token is valid
        """
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict[str, Any]) -> tuple[WebhookEventType, CanonicalTicket]:
        """Parse a raw webhook payload into canonical form.
        
        This is where field_mapping from config.yaml is applied.
        
        Args:
            payload: Parsed JSON body of the webhook
            
        Returns:
            Tuple of (event_type, canonical_ticket)
        """
        ...

    @abstractmethod
    def enrich_context(self, ticket: CanonicalTicket) -> EnrichedContext:
        """Fetch additional context from info repositories.
        
        Args:
            ticket: The canonical ticket to enrich
            
        Returns:
            EnrichedContext with repository data attached
        """
        ...

    @abstractmethod
    def execute_action(self, decision: AgentDecision, ticket: CanonicalTicket) -> ActionResult:
        """Execute the decided action on the client's backend.
        
        Args:
            decision: What the AI agent decided to do
            ticket: The canonical ticket being acted on
            
        Returns:
            ActionResult indicating success/failure
        """
        ...

    # ------------------------------------------------------------------
    # Standard pipeline — NOT abstract, this is in Rauda Core
    # ------------------------------------------------------------------

    def handle_webhook(self, headers: dict[str, str], body: bytes, payload: dict[str, Any]) -> ActionResult:
        """Standard webhook handling pipeline.
        
        This method is NOT overridden by integrations. It orchestrates the
        standard flow using the abstract methods above.
        
        Pipeline: validate → parse → enrich → [AI decision] → execute
        """
        # Step 1: Authenticate
        if not self.validate_webhook(headers, body):
            return ActionResult(
                success=False,
                action_type=ActionType.ESCALATE_TO_HUMAN,
                message="Webhook authentication failed",
            )

        # Step 2: Parse into canonical form
        event_type, ticket = self.parse_webhook(payload)

        # Step 3: Check if we handle this event type
        if event_type not in self.config.webhook.subscribed_events:
            return ActionResult(
                success=True,
                action_type=ActionType.ESCALATE_TO_HUMAN,
                message=f"Event type {event_type.value} not subscribed, skipping",
            )

        # Step 4: Enrich with context from info repositories
        enriched = self.enrich_context(ticket)

        # Step 5: AI decision (stub — would call LLM in production)
        decision = self._get_ai_decision(enriched)

        # Step 6: Execute the action
        result = self.execute_action(decision, ticket)

        return result

    def _get_ai_decision(self, enriched: EnrichedContext) -> AgentDecision:
        """Placeholder for AI agent decision-making.
        
        In production this calls the LLM with enriched context.
        Override in tests with a mock decision.
        """
        return AgentDecision(
            action_type=ActionType.REPLY_TO_TICKET,
            confidence=0.0,
            reasoning="Stub decision — LLM not connected",
            reply_text="",
        )
