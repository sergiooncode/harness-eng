# Adding a New Client Integration

> This guide is for the AI agent (or non-developer) creating a new client
> integration. Follow these steps in order. Run the harness after each step.

## Step 1: Create the client directory

```bash
mkdir clients/<client_slug>
```

The slug must be lowercase, alphanumeric, with underscores or hyphens only.

## Step 2: Create config.yaml

Create `clients/<client_slug>/config.yaml` using this template:

```yaml
client_name: "Human-Readable Client Name"
client_slug: "<client_slug>"
platform: "zendesk"  # or "intercom"

webhook:
  subscribed_events:
    - ticket_created        # pick from: ticket_created, ticket_updated,
    - ticket_updated        #            ticket_comment_added, ticket_closed
  auth_method: "hmac_signature"  # pick from: bearer_token, hmac_signature, api_key
  auth_secret_env_var: "CLIENT_ZENDESK_SECRET"  # env var name holding the secret

field_mapping:
  ticket_id: "id"
  subject: "subject"
  description: "description"
  requester_email: "requester.email"
  requester_name: "requester.name"
  status: "status"
  priority: "priority"
  tags: "tags"
  custom_fields:
    # Map canonical names to Zendesk custom field paths
    # order_id: "custom_fields.order_number"

info_repositories:
  - name: "Repository Name"
    type: "api"           # pick from: api, database, knowledge_base, airtable
    description: "What this repository contains and when to query it"
    base_url: "https://..."
    auth_env_var: "CLIENT_API_KEY"

actions:
  - name: "Reply to Ticket"
    action_type: "reply_to_ticket"  # pick from: reply_to_ticket, update_ticket_status,
    description: "What this action does"  #   escalate_to_human, tag_ticket, call_client_api
    endpoint: "https://..."
    requires_confirmation: false

eval:
  airtable_base_id: "appXXXX"
  airtable_table_name: "Reply Evaluations"
  auto_eval_enabled: false
  quality_threshold: 0.7
```

**Run the harness to validate:**
```bash
python -m harness.harness check clients/<client_slug>/
```

Fix any issues reported in the JSON output before proceeding.

## Step 3: Create integration.py

Create `clients/<client_slug>/integration.py`. Your class MUST:
- Subclass `BaseIntegration` from `harness.integrations.base`
- Implement exactly 4 methods: `validate_webhook`, `parse_webhook`, `enrich_context`, `execute_action`
- NOT override `handle_webhook` or `_get_ai_decision`

Use `clients/acme_corp/integration.py` as a reference implementation.

**Run the harness again to validate:**
```bash
python -m harness.harness check clients/<client_slug>/
```

## Step 4: Verify cross-client consistency

```bash
python -m harness.harness check-all clients/
```

Review the `consistency.issues` in the output. Warnings about field drift
or action gaps may be intentional — confirm and document in config.yaml comments.

## What NOT to do

- Do NOT import from `harness.validators`, `harness.harness`, or `harness.registry`
- Do NOT make HTTP calls inside `parse_webhook` — it must be a pure data transformation
- Do NOT override `handle_webhook` — the standard pipeline is in `BaseIntegration`
- Do NOT create multiple `BaseIntegration` subclasses in one file
