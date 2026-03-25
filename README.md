# harness-eng

Rauda's core platform for AI-powered customer support ticket handling. Provides a pluggable framework for evaluating ticket replies and onboarding new clients with minimal configuration.

## Architecture

```
rauda_core/          # Reusable framework — interfaces, schemas, standard implementations
  interfaces/        # Base classes for extension points (ResultWriter, BaseIntegration)
  schemas.py         # Shared data models (Evaluation, ClientConfig, enums)
  config.py          # Client config loading from YAML
  writers/           # Writer implementations (CSV, Airtable)
  integrations/      # Integration implementations (DefaultIntegration) + registry

evaluator/           # Ticket reply evaluation via GPT-4o
  client.py          # Async OpenAI evaluation calls
  csv_io.py          # CSV reading

clients/             # Per-client configuration (one folder per client)
  acme_corp/         # Config-only client
  globex/            # Config-only client
  broken_corp/       # Deliberately broken client for harness testing

harness/             # Auto-discovers and validates all extension points
  harness.py         # CLI entry point
  validators/        # Structural linter, schema validator, consistency checker

golden/              # Behavioral contracts (input/expected output pairs)
docs/                # ADRs, invariants, anti-patterns
```

## Extension Points

All extension points follow the same pattern:

1. **Base interface** in `rauda_core/interfaces/` (ABC)
2. **Default implementation** in `rauda_core/<type>/` (config-driven, covers common case)
3. **Optional custom implementation** in `clients/<slug>/` (subclass when config isn't enough)

Current extension points:

| Extension | Interface | Default Implementation | Purpose |
|-----------|-----------|----------------------|---------|
| Writers | `ResultWriter` | `CsvWriter`, `AirtableWriter` | Output evaluation results |
| Integrations | `BaseIntegration` | `DefaultIntegration` | Webhook auth, field mapping, enrichment, actions |

## Setup

Requires Python 3.12+ and Docker.

1. Create a `.env` file:

```
OPENAI_API_KEY=sk-...

# For Airtable output (default):
AIRTABLE_API_TOKEN=pat...
AIRTABLE_BASE_ID=app...
AIRTABLE_TABLE_NAME=...

# Or set CLIENT_CONFIG to point to a YAML config file
```

2. Place ticket/reply pairs in `resources/tickets.csv`.

## Usage

### Run evaluation pipeline

```bash
make run
```

Reads tickets from CSV, evaluates each via GPT-4o, writes results to Airtable (or CSV via config).

### Run tests

```bash
make test
```

### Run harness validation

```bash
python -m harness.harness check-all clients/
```

The harness auto-discovers all writers and client integrations, validates them against their base interfaces, checks config schemas, and runs golden dataset behavioral checks. Output is structured JSON with fix hints.

## Onboarding a New Client

1. Create `clients/<client_name>/config.yaml` with the required fields (see `rauda_core/schemas.py` for the `ClientConfig` schema).
2. Run `python -m harness.harness check-all clients/` to validate.
3. If the client needs custom behavior beyond what config supports, add an `integration.py` that subclasses `DefaultIntegration` and overrides the relevant methods.

No changes to `rauda_core/` are needed.

## What's Been Done

Per the goals in CLAUDE.md:

- **Extracted reusable parts into `rauda_core/`**: base interfaces (`ResultWriter`, `BaseIntegration`), shared schemas and enums, client config loading, standard implementations (`CsvWriter`, `AirtableWriter`, `DefaultIntegration`), and the client registry.
- **Made extension points pluggable**: each has an ABC in `rauda_core/interfaces/`, a default implementation, and the pipeline is implementation-agnostic. `evaluate.py` uses `ResultWriter` without knowing which writer it gets.
- **Built the harness**: auto-discovers writers in `rauda_core/writers/` and integrations in `clients/*/`, validates structural conformance via AST linting, checks config schemas, and runs consistency checks. No per-implementation harness code. Outputs structured JSON with `next_steps` for AI agent self-correction.
- **Created grounding material**: golden datasets for writers and integrations, ADR for extension point architecture, `docs/invariants.yaml`, `docs/anti-patterns.yaml`.
- **Preserved the evaluator flow**: `evaluate.py` still reads CSV, evaluates via GPT-4o, and writes results. Default output is now Airtable (configurable via env vars or YAML config).
- **Config-only client onboarding**: clients like `acme_corp` and `globex` have only a `config.yaml` — `DefaultIntegration` handles them automatically.
