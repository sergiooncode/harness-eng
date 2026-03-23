# Rauda Core — Architecture

> This document is the SINGLE MAP of the codebase. If you are an AI agent
> working on this repo, read this first. Everything you need to know about
> where things are and how they connect is here.

## Directory Structure

```
harness-eng/
├── harness/                     # The framework — DO NOT modify per-client
│   ├── schema.py                   # Typed contracts (ClientConfig, enums)
│   ├── harness.py                  # The harness entry point (agent runs this)
│   ├── registry.py                 # Auto-discovery and loading of integrations
│   ├── integrations/
│   │   └── base.py                 # Abstract base class + canonical data types
│   ├── validators/
│   │   ├── schema_validator.py     # Config.yaml validation
│   │   ├── structural_linter.py    # AST-based integration.py enforcement
│   │   └── consistency_checker.py  # Cross-client drift detection
│   └── evals/
│       └── spec_compliance.py      # Spec compliance eval (deterministic + optional LLM)
├── clients/                        # Per-client integrations — ONE directory each
│   ├── acme_corp/
│   │   ├── config.yaml             # Client configuration
│   │   └── integration.py          # Client integration code
│   └── globex/
│       ├── config.yaml
│       └── integration.py
└── docs/
    └── ARCHITECTURE.md             # This file
```

## Data Flow

```
Zendesk Webhook → validate_webhook() → parse_webhook() → CanonicalTicket
                                                              ↓
                                                        enrich_context()
                                                              ↓
                                                        EnrichedContext
                                                              ↓
                                                      _get_ai_decision()  [Rauda Core]
                                                              ↓
                                                        AgentDecision
                                                              ↓
                                                       execute_action()
                                                              ↓
                                                        ActionResult
```

## Layered Architecture

Dependencies flow in ONE direction:

    schema.py → integrations/base.py → validators/ → harness.py → registry.py

- `schema.py` depends on nothing (only stdlib)
- `integrations/base.py` depends on `schema.py`
- `validators/` depend on `schema.py` (and `base.py` for structural checks)
- `harness.py` depends on `validators/` and `evals/`
- `registry.py` depends on `schema.py` and `integrations/base.py`
- Client `integration.py` files depend on `schema.py` and `integrations/base.py` ONLY

## Rules

1. **Client integrations MUST NOT import from validators/, harness.py, or registry.py**
2. **Client integrations MUST NOT override handle_webhook** — it's the standard pipeline
3. **Client integrations MUST NOT override _get_ai_decision** — AI logic lives in Rauda Core
4. **parse_webhook MUST be a pure transformation** — no HTTP calls, no side effects
5. **All knowledge lives in this repo** — if it's not here, the agent can't use it

## The Harness

The harness is invoked by the AI agent to validate its own work:

```bash
# Check a single client
python -m harness.harness check clients/<client_slug>/

# Check all clients + cross-client consistency
python -m harness.harness check-all clients/

# Evaluate implementation against challenge spec
# Deterministic checks always run; LLM layer activates if ANTHROPIC_API_KEY is set
python -m harness.harness eval --spec spec.md --target clients/<client_slug>/
```

Output is ALWAYS structured JSON. Exit code 0 = passed, 1 = failed.
The `next_steps` array tells the agent exactly what to fix.

## Adding a New Client

See docs/INTEGRATION_GUIDE.md
