"""Shared data models for Rauda Core.

Contains both evaluation schemas (used by the evaluator pipeline) and
client configuration schemas (used by integrations and the harness).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Evaluation schemas (evaluator pipeline)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert evaluator of customer support replies.

Given a customer support ticket and an AI-generated reply, evaluate the reply on three dimensions:

1. **Content** (relevance, correctness, completeness):
   - Does the reply address the customer's issue?
   - Is the information provided accurate?
   - Does it cover everything the customer needs to know?

2. **Format** (clarity, structure, grammar/spelling):
   - Is the reply clearly written and easy to understand?
   - Is it well-structured and appropriately concise?
   - Is it free of grammar and spelling errors?

3. **Empathy** (validation, clarity, ownership):
   - Does the reply acknowledge the customer’s feelings or situation in a believable way?
   - Does the reply clearly explain the next step or answer without sounding cold or defensive?
   - Does the reply take responsibility for helping, rather than shifting burden to the customer?

Score each dimension from 1 to 5.

Provide a brief explanation (1-2 sentences) for each score.\
"""


class Evaluation(BaseModel):
    """Structured evaluation result from GPT-4o."""

    content_score: int = Field(ge=1, le=5, description="Content score from 1 to 5")
    content_explanation: str = Field(description="Brief explanation of the content score")
    format_score: int = Field(ge=1, le=5, description="Format score from 1 to 5")
    format_explanation: str = Field(description="Brief explanation of the format score")
    empathy_score: int = Field(ge=1, le=5, description="Empathy score from 1 to 5")
    empathy_explanation: str = Field(description="Brief explanation of the empathy score")


# ---------------------------------------------------------------------------
# Enums — constrained vocabulary for the integration surface
# ---------------------------------------------------------------------------

class SupportPlatform(str, Enum):
    ZENDESK = "zendesk"
    INTERCOM = "intercom"


class WebhookEventType(str, Enum):
    TICKET_CREATED = "ticket_created"
    TICKET_UPDATED = "ticket_updated"
    TICKET_COMMENT_ADDED = "ticket_comment_added"
    TICKET_CLOSED = "ticket_closed"


class ActionType(str, Enum):
    REPLY_TO_TICKET = "reply_to_ticket"
    UPDATE_TICKET_STATUS = "update_ticket_status"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    TAG_TICKET = "tag_ticket"
    CALL_CLIENT_API = "call_client_api"


# ---------------------------------------------------------------------------
# Client config schema — what goes in config.yaml per client
# ---------------------------------------------------------------------------

@dataclass
class WebhookConfig:
    """Which events this client subscribes to and how to authenticate them."""
    subscribed_events: list[WebhookEventType]
    auth_method: Literal["bearer_token", "hmac_signature", "api_key"]
    auth_secret_env_var: str  # name of env var holding the secret


@dataclass
class InfoRepository:
    """An info source the agent can query to enrich context for a ticket."""
    name: str
    type: Literal["api", "database", "knowledge_base", "airtable"]
    description: str  # plain-language description for AI agent context
    base_url: str = ""
    auth_env_var: str = ""


@dataclass
class ClientAction:
    """An action the agent can take on the client's backend."""
    name: str
    action_type: ActionType
    description: str  # plain-language description for AI agent context
    endpoint: str = ""  # URL template if applicable
    requires_confirmation: bool = False  # human-in-the-loop gate


@dataclass
class EvalConfig:
    """Configuration for how AI-generated replies are evaluated for this client."""
    airtable_base_id: str = ""
    airtable_table_name: str = "Reply Evaluations"
    auto_eval_enabled: bool = False
    quality_threshold: float = 0.7  # minimum score to auto-send


@dataclass
class FieldMapping:
    """Maps platform-specific field names to Rauda's canonical field names.

    This is the key standardization point — different Zendesk instances
    may use different custom fields, but Rauda Core works with canonical names.
    """
    ticket_id: str = "id"
    subject: str = "subject"
    description: str = "description"
    requester_email: str = "requester.email"
    requester_name: str = "requester.name"
    status: str = "status"
    priority: str = "priority"
    tags: str = "tags"
    custom_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ClientConfig:
    """Top-level config for a client integration.

    This is what a non-developer fills in (via config.yaml) to onboard a new client.
    The harness validates this config mechanically before anything runs.
    """
    client_name: str
    client_slug: str  # unique identifier, lowercase, no spaces
    platform: SupportPlatform
    webhook: WebhookConfig
    field_mapping: FieldMapping
    info_repositories: list[InfoRepository] = field(default_factory=list)
    actions: list[ClientAction] = field(default_factory=list)
    eval: EvalConfig = field(default_factory=EvalConfig)

    def __post_init__(self):
        if not self.client_slug.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"client_slug must be alphanumeric with underscores/hyphens, "
                f"got: '{self.client_slug}'"
            )
        if self.client_slug != self.client_slug.lower():
            raise ValueError(
                f"client_slug must be lowercase, got: '{self.client_slug}'"
            )
