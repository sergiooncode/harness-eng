# ADAPTATION PROMPT

Use this prompt with Claude Code or Cursor once you see the actual challenge.
Copy everything below the line and paste it, replacing the placeholder.

---

## Prompt:

I have a working engineering harness at `harness/` built for Zendesk client integrations. It has these patterns that MUST be preserved:

1. **schema.py** — typed dataclasses + enums defining the contract (what a valid integration must provide)
2. **integrations/base.py** — abstract base class with a standard pipeline (template method pattern). Client code implements abstract methods, never overrides the pipeline.
3. **validators/schema_validator.py** — validates config.yaml against the schema. Every error includes the field path and an actionable fix hint.
4. **validators/structural_linter.py** — AST-based checks on integration code (required methods implemented, forbidden patterns caught, architectural rules enforced)
5. **validators/consistency_checker.py** — cross-integration drift detection (finds inconsistencies across multiple client implementations)
6. **eval/reply_eval.py** — deterministic quality checks on AI-generated outputs
7. **harness.py** — single CLI entry point (`python -m harness.harness check <dir>`) that runs all validators and returns structured JSON with `passed`, `checks`, `next_steps` (with fix hints). Exit code 0 = pass, 1 = fail.
8. **docs/ARCHITECTURE.md** — codebase map for the AI agent
9. **docs/INTEGRATION_GUIDE.md** — step-by-step instructions for creating a new integration
10. **clients/** — example implementations (config.yaml + integration.py per client)

The harness output is designed to be read by an AI agent to self-correct. Every error message must be specific enough that the agent knows exactly what to fix without human help.

Here is the actual challenge I need to solve:

```
Wire up the LLM eval stubs
```

**Your task:**

1. Read every file in `harness/` and `clients/` to understand the current patterns.
2. Identify what domain the challenge is about (it may or may not be Zendesk integrations).
3. If the domain matches (Zendesk/Intercom integrations), keep the code as-is and extend it to solve the challenge.
4. If the domain is different, reshape all the domain-specific parts while keeping the same architectural patterns:
   - Replace enums, dataclasses in schema.py with the challenge's domain vocabulary
   - Replace the abstract methods in base.py with what the challenge's pipeline requires
   - Update validators to check the challenge's specific rules
   - Update eval checks for the challenge's output type
   - Update harness.py check methods accordingly
   - Update ARCHITECTURE.md and INTEGRATION_GUIDE.md
   - Create 2 example client implementations that pass the harness
5. After making changes, run `python -m harness.harness check-all clients/` and confirm all checks pass.
6. Then create one deliberately broken client and run the harness on it to confirm errors are caught with actionable messages.

**Critical rules:**
- Zero external dependencies (stdlib + pyyaml only)
- All harness output must be structured JSON parseable by an AI agent
- Every error must include a fix_hint telling the agent exactly what to change
- The harness must be invocable as `python -m harness.harness check <path>`
- Do NOT ask me questions. Make reasonable decisions and proceed.
