# Context

This repo contains Rauda's core platform code. Rauda is an AI agentic layer
that handles customer support tickets for multiple clients. The codebase has
extension points that the Engagement team adds to for each new client
(writers, integrations, and any future extension types).

These are currently ad-hoc per client and need standardization into `rauda_core/`.

# Goal

Standardize `rauda_core/` so the Engagement team (using AI tools like Claude Code)
can onboard a new client by writing only:
- A config file (YAML)
- Optionally a custom implementation of an extension point

They never touch `rauda_core/`. The harness verifies their work automatically.

# Repo Conventions

```
rauda_core/          # Reusable framework. Staff engineer owns. Never client-specific.
  interfaces/        # Base classes for all extension points
  schemas.py         # Shared data models
  config.py          # Client config loading
  <extension_type>/  # Standard implementations per extension point (writers/, etc.)

clients/             # Per-client code. Engagement team owns. One folder per client.

harness/             # Auto-discovers and validates all extension points

golden/              # Behavioral contracts. shared/input.json + per-type expected outputs.

docs/
  adr/               # Architecture decisions. AI reads before making design choices.
  invariants.yaml    # Business rules as assertions.
  anti-patterns.yaml # Mistakes with context.
```

When a new extension point is added, it gets a base class in `interfaces/`,
a directory for implementations, and golden dataset entries. The harness
auto-discovers it. This file doesn't change.

# Task

1. Extract reusable parts into `rauda_core/`:
   - Base interfaces for each extension point
   - Shared schemas and data models
   - Client config loading from YAML
   - Standard implementations

2. Make extension points pluggable:
   - Each has a base class in interfaces/
   - New implementations subclass it
   - The pipeline doesn't know which implementation it's using

3. Build the harness (`python -m harness check-all`):
   - Auto-discovers any subclass of a base interface
   - Validates: structural conformance, config schema, interface compliance
   - Runs golden dataset behavioral checks (input → expected output)
   - No per-implementation harness code. Written once.
   - Output is structured JSON with fix hints for AI agent self-correction

4. Create grounding material:
   - `golden/` — deterministic input/output pairs for behavioral contracts
   - `docs/adr/` — architecture decision records
   - `docs/invariants.yaml` — business rules as checkable assertions
   - `docs/anti-patterns.yaml` — mistakes with context on why they're wrong

5. Ensure existing evaluator flow (CSV in → GPT-4o eval → CSV out) still works.

# Rules

- Do not break the existing evaluate.py flow
- rauda_core/ is generic — no client-specific code in it
- Client-specific code lives in clients/ only
- After every code change, run `python -m harness check-all` and read the JSON output.
  If any check fails, fix what `next_steps` say before moving on.
  Do not ask me — use the harness output to self-correct.
- Before making design choices, read docs/adr/, docs/invariants.yaml, and
  docs/anti-patterns.yaml. Do not contradict them.
- Before adding a new implementation, check golden/ for expected behavior.
- PEP-8, type hints, docstrings
- If stuck for more than 2 minutes, simplify the approach
- harness/ only contains validation code. It checks things, it never implements business logic.
- rauda_core/ contains interfaces, schemas, writers, and standard implementations.
- The harness imports from rauda_core to know what to validate against. rauda_core never imports from harness.

# Decisions

-
