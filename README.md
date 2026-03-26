# harness-eng

Rauda's core platform for AI-powered customer support ticket handling. Provides a pluggable framework for evaluating ticket replies and onboarding new clients with minimal configuration.

## Architecture

```
rauda_core/          # Reusable framework — interfaces, schemas, standard implementations
  interfaces/        # Base classes for extension points (ResultWriter, BaseIntegration, BaseStep)
  schemas.py         # Shared data models (Evaluation, ClientConfig, enums)
  config.py          # Client config loading from YAML
  writers/           # Writer implementations (CSV, Airtable)
  integrations/      # Integration implementations (DefaultIntegration) + registry
  workflows/         # Workflow step implementations (LlmStep, CodeStep) + runner

evaluator/           # Ticket reply evaluation via GPT-4o
  client.py          # Async OpenAI evaluation calls
  csv_io.py          # CSV reading

clients/             # Per-client configuration (one folder per client)
  acme_corp/         # Config-only client with workflow
  globex/            # Config-only client
  broken_corp/       # Deliberately broken client for harness testing

harness/             # Auto-discovers and validates all extension points
  harness.py         # CLI entry point + validator registry
  validators/        # Schema validators, structural linter, consistency checker, golden validator

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
| Workflows | `BaseStep` | `LlmStep`, `CodeStep` | Orchestrated step-by-step ticket handling |

## Harness

The harness uses a **validator registry** — a dict mapping client artifact filenames to validators:

```python
CLIENT_VALIDATORS = {
    "config.yaml": ConfigValidator(),
    "integration.py": StructuralLinter(base_class_name="BaseIntegration", ...),
    "workflow.yaml": WorkflowValidator(),
}
```

`check_client` scans a client directory and runs every registered validator against matching files. Adding a new extension point means adding one line to the registry — no harness logic changes.

Writers are validated separately via auto-discovery of `rauda_core/writers/*.py`, with structural linting and golden dataset checks.

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

Output is structured JSON with fix hints for AI agent self-correction.

## Onboarding a New Client

1. Create `clients/<client_name>/config.yaml` (see `rauda_core/schemas.py` for the `ClientConfig` schema).
2. Optionally add `workflow.yaml` to define the ticket handling steps.
3. Run `python -m harness.harness check-all clients/` to validate.
4. If the client needs custom behavior, add `integration.py` subclassing `DefaultIntegration`.

No changes to `rauda_core/` are needed.

## What's Been Done

Per the goals in CLAUDE.md:

- **Extracted reusable parts into `rauda_core/`**: base interfaces (`ResultWriter`, `BaseIntegration`, `BaseStep`), shared schemas and enums, client config loading, standard implementations (`CsvWriter`, `AirtableWriter`, `DefaultIntegration`, `LlmStep`, `CodeStep`, `WorkflowRunner`), and the client registry.
- **Made extension points pluggable**: each has an ABC in `rauda_core/interfaces/`, a default implementation, and the pipeline is implementation-agnostic.
- **Built the harness with registry-based validation**: a `CLIENT_VALIDATORS` dict maps filenames to validators. `check_client` loops over the registry — no per-artifact if/else chains. Adding a new extension point = one line in the registry. Writers are auto-discovered from `rauda_core/writers/`. Golden dataset behavioral checks validate deterministic input/output contracts.
- **Created grounding material**: golden datasets for writers and integrations, ADR for extension point architecture, `docs/invariants.yaml`, `docs/anti-patterns.yaml`.
- **Preserved the evaluator flow**: `evaluate.py` still reads CSV, evaluates via GPT-4o, and writes results. Default output is Airtable (configurable via env vars or YAML config).
- **Config-only client onboarding**: clients like `acme_corp` and `globex` need only a `config.yaml` — `DefaultIntegration` handles them automatically.
- **Workflow orchestration**: linear step pipeline where each step reads from and writes to a shared context dict. Steps are either LLM calls or code functions, defined declaratively in `workflow.yaml`. The harness validates step structure, model presence, output key uniqueness, and input key dependencies.
