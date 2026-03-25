# ADR-001: Extension Point Architecture

## Status

Accepted

## Context

Rauda onboards new clients frequently. Each client needs webhook auth, field mapping,
context enrichment, and action execution — but the logic is 90% identical across clients.
The Engagement team (non-engineers using AI tools) does the onboarding. They need a
process that is config-driven and mechanically verifiable.

## Decision

All extension points follow one pattern:

1. **Base interface** in `rauda_core/interfaces/` — defines the contract (ABC).
2. **Default implementation** in `rauda_core/<extension_type>/` — covers the common case
   using config alone. No code required for standard clients.
3. **Custom implementation** in `clients/<slug>/` — only when a client needs behaviour
   that config cannot express. Subclasses the default, overrides one method.
4. **Harness validation** in `harness/` — auto-discovers all implementations and
   validates them structurally. No per-implementation harness code.

Current extension points:
- **Writers** (`ResultWriter`): CSV, Airtable. Output layer for evaluation results.
- **Integrations** (`BaseIntegration`): Webhook handling pipeline. `DefaultIntegration`
  covers HMAC, bearer token, and API key auth from config.

## Consequences

- New clients are onboarded with a `config.yaml` file only.
- Custom code is the exception, not the rule.
- The harness catches structural errors before runtime.
- `rauda_core/` never contains client-specific code.
- Adding a new extension point means: one interface in `interfaces/`, one default
  implementation, and golden dataset entries. The harness auto-discovers it.
