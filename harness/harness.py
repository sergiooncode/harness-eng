"""
harness/harness.py — The engineering harness for AI-agent-driven development.

This is the SINGLE ENTRY POINT that an AI agent (Claude Code, Cursor, etc.)
invokes to validate its own work. The agent runs this, reads the structured
JSON output, and uses it to self-correct.

Usage by an AI agent:
    python -m harness.harness check clients/new_client/
    python -m harness.harness check-all clients/
    python -m harness.harness eval --reply "Hello, ..." --subject "Order issue"

The output is ALWAYS structured JSON so the agent can parse it programmatically.
The error messages are ACTIONABLE — they tell the agent exactly what to fix.
"""

import json
import sys
from pathlib import Path
from typing import Any

from harness.validators.schema_validator import ConfigValidator
from harness.validators.structural_linter import StructuralLinter
from harness.validators.consistency_checker import ConsistencyChecker
from harness.eval.reply_eval import ReplyEvaluator


class Harness:
    """The harness the AI agent runs against its own output."""

    def __init__(self):
        self.config_validator = ConfigValidator()
        self.structural_linter = StructuralLinter()
        self.consistency_checker = ConsistencyChecker()
        self.reply_evaluator = ReplyEvaluator()

    def check_client(self, client_dir: Path) -> dict[str, Any]:
        """Run all harness checks on a single client integration.

        Returns structured JSON the agent can parse and act on.
        """
        client_dir = Path(client_dir)
        result = {
            "client": client_dir.name,
            "passed": True,
            "checks": {},
            "summary": "",
            "next_steps": [],
        }

        # --- Check 1: Does the directory structure exist? ---
        config_path = client_dir / "config.yaml"
        integration_path = client_dir / "integration.py"

        structure_issues = []
        if not client_dir.exists():
            structure_issues.append(f"Directory {client_dir} does not exist. Create it first.")
        if not config_path.exists():
            structure_issues.append(
                f"Missing {config_path}. Create config.yaml following the schema in "
                f"harness/schema.py — see ClientConfig dataclass for all required fields."
            )
        if not integration_path.exists():
            structure_issues.append(
                f"Missing {integration_path}. Create integration.py with a class that "
                f"subclasses BaseIntegration from harness.integrations.base and implements: "
                f"validate_webhook, parse_webhook, enrich_context, execute_action."
            )

        result["checks"]["structure"] = {
            "passed": len(structure_issues) == 0,
            "issues": structure_issues,
        }
        if structure_issues:
            result["passed"] = False
            result["summary"] = "Missing files. See next_steps."
            result["next_steps"] = structure_issues
            return result

        # --- Check 2: Config schema validation ---
        config_errors = self.config_validator.validate_file(config_path)
        config_issues = []
        for err in config_errors:
            config_issues.append({
                "field": err.path,
                "message": err.message,
                "severity": err.severity,
                "fix_hint": self._config_fix_hint(err.path, err.message),
            })

        config_passed = not any(e.severity == "error" for e in config_errors)
        result["checks"]["config_schema"] = {
            "passed": config_passed,
            "file": str(config_path),
            "issues": config_issues,
        }
        if not config_passed:
            result["passed"] = False

        # --- Check 3: Structural linting of integration.py ---
        lint_issues = self.structural_linter.lint_file(integration_path)
        lint_items = []
        for issue in lint_issues:
            lint_items.append({
                "rule": issue.rule,
                "line": issue.line,
                "message": issue.message,
                "severity": issue.severity,
                "fix_hint": self._lint_fix_hint(issue.rule),
            })

        lint_passed = not any(i.severity == "error" for i in lint_issues)
        result["checks"]["structural_lint"] = {
            "passed": lint_passed,
            "file": str(integration_path),
            "issues": lint_items,
        }
        if not lint_passed:
            result["passed"] = False

        # --- Check 4: Try to actually load the integration ---
        load_result = self._try_load(client_dir, config_path, integration_path)
        result["checks"]["load"] = load_result
        if not load_result["passed"]:
            result["passed"] = False

        # --- Build summary and next_steps ---
        result["summary"] = self._build_summary(result)
        result["next_steps"] = self._build_next_steps(result)

        return result

    def check_all(self, clients_dir: Path) -> dict[str, Any]:
        """Run harness on all clients + cross-client consistency checks."""
        clients_dir = Path(clients_dir)
        result = {
            "passed": True,
            "clients": {},
            "consistency": {},
            "summary": "",
        }

        # Check each client individually
        if clients_dir.exists():
            for client_dir in sorted(clients_dir.iterdir()):
                if client_dir.is_dir() and not client_dir.name.startswith("."):
                    client_result = self.check_client(client_dir)
                    result["clients"][client_dir.name] = client_result
                    if not client_result["passed"]:
                        result["passed"] = False

        # Cross-client consistency
        consistency_issues = self.consistency_checker.check_all(clients_dir)
        consistency_items = []
        for issue in consistency_issues:
            consistency_items.append({
                "client": issue.client,
                "category": issue.category,
                "message": issue.message,
                "severity": issue.severity,
            })

        result["consistency"] = {
            "passed": not any(i.severity == "error" for i in consistency_issues),
            "issues": consistency_items,
        }

        # Summary
        total = len(result["clients"])
        passed = sum(1 for c in result["clients"].values() if c["passed"])
        result["summary"] = f"{passed}/{total} clients passed all checks."

        return result

    def eval_reply(self, reply_text: str, subject: str = "", description: str = "",
                   quality_threshold: float = 0.7) -> dict[str, Any]:
        """Evaluate an AI-generated reply. Agent calls this to check its own output."""
        evaluator = ReplyEvaluator(quality_threshold=quality_threshold)
        eval_result = evaluator.evaluate(reply_text, subject, description)

        return {
            "passed": eval_result.passed,
            "overall_score": round(eval_result.overall_score, 3),
            "quality_threshold": quality_threshold,
            "checks": {
                name: {
                    "passed": check.passed,
                    "score": round(check.score, 3),
                    "message": check.message,
                }
                for name, check in eval_result.checks.items()
            },
            "failed_checks": eval_result.failed_checks,
        }

    # ------------------------------------------------------------------
    # Helpers — actionable hints for the AI agent
    # ------------------------------------------------------------------

    def _config_fix_hint(self, field_path: str, message: str) -> str:
        """Return a specific, actionable fix hint the agent can follow."""
        hints = {
            "client_name": "Add 'client_name: \"Your Client Name\"' to config.yaml",
            "client_slug": "Add 'client_slug: \"your_client\"' (lowercase, alphanumeric with _ or -)",
            "platform": "Add 'platform: \"zendesk\"' or 'platform: \"intercom\"'",
            "webhook": "Add a 'webhook:' section with subscribed_events, auth_method, auth_secret_env_var",
            "field_mapping": "Add a 'field_mapping:' section. See harness/schema.py FieldMapping for defaults.",
        }
        for key, hint in hints.items():
            if key in field_path:
                return hint
        return f"Fix the field at '{field_path}'. Refer to harness/schema.py for the expected shape."

    def _lint_fix_hint(self, rule: str) -> str:
        hints = {
            "STRUCT-001": (
                "Your integration.py must define a class that inherits from BaseIntegration. "
                "Example: 'class MyClientIntegration(BaseIntegration):'"
            ),
            "STRUCT-002": "Remove the extra BaseIntegration subclass. Only one per file.",
            "STRUCT-003": (
                "Implement the missing method. Required methods: "
                "validate_webhook, parse_webhook, enrich_context, execute_action. "
                "See harness/integrations/base.py for signatures."
            ),
            "STRUCT-004": (
                "Remove your handle_webhook override. The standard pipeline in "
                "BaseIntegration.handle_webhook calls your methods in order. "
                "Do not override it."
            ),
            "STRUCT-005": (
                "Remove _get_ai_decision override. AI decision logic is in Rauda Core, "
                "not in client integrations."
            ),
            "PURE-001": (
                "parse_webhook must be a pure data transformation — no HTTP calls. "
                "Move any HTTP/API calls to enrich_context or execute_action."
            ),
        }
        return hints.get(rule, f"See harness/validators/structural_linter.py for rule {rule}")

    def _try_load(self, client_dir: Path, config_path: Path, integration_path: Path) -> dict:
        """Try to actually import and instantiate the integration."""
        try:
            from harness.registry import _load_config_from_yaml, _load_integration_class
            config = _load_config_from_yaml(config_path)
            cls = _load_integration_class(integration_path)
            instance = cls(config)
            return {
                "passed": True,
                "integration_class": cls.__name__,
                "message": f"Successfully loaded {cls.__name__} with config '{config.client_name}'",
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "fix_hint": (
                    f"The integration failed to load: {e}. "
                    f"Check that config.yaml values match the schema enums "
                    f"and that integration.py imports are correct."
                ),
            }

    def _build_summary(self, result: dict) -> str:
        if result["passed"]:
            return f"Client '{result['client']}' passed all harness checks."
        failed = [name for name, check in result["checks"].items() if not check["passed"]]
        return f"Client '{result['client']}' FAILED checks: {', '.join(failed)}."

    def _build_next_steps(self, result: dict) -> list[str]:
        steps = []
        for check_name, check in result["checks"].items():
            if not check["passed"]:
                if "issues" in check:
                    for issue in check["issues"]:
                        if isinstance(issue, dict) and "fix_hint" in issue:
                            steps.append(issue["fix_hint"])
                        elif isinstance(issue, str):
                            steps.append(issue)
                elif "fix_hint" in check:
                    steps.append(check["fix_hint"])
        return steps


# ------------------------------------------------------------------
# CLI interface — what the agent actually invokes
# ------------------------------------------------------------------

def main():
    harness = Harness()

    if len(sys.argv) < 2:
        usage = {
            "error": "No command specified",
            "usage": {
                "check <client_dir>": "Run all harness checks on a single client",
                "check-all <clients_dir>": "Run harness on all clients + consistency checks",
                "eval --reply <text> [--subject <text>] [--description <text>]": "Evaluate an AI reply",
            },
        }
        print(json.dumps(usage, indent=2))
        sys.exit(1)

    command = sys.argv[1]

    if command == "check" and len(sys.argv) >= 3:
        result = harness.check_client(Path(sys.argv[2]))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    elif command == "check-all" and len(sys.argv) >= 3:
        result = harness.check_all(Path(sys.argv[2]))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    elif command == "eval":
        # Parse --reply, --subject, --description from args
        args = sys.argv[2:]
        reply = subject = description = ""
        i = 0
        while i < len(args):
            if args[i] == "--reply" and i + 1 < len(args):
                reply = args[i + 1]; i += 2
            elif args[i] == "--subject" and i + 1 < len(args):
                subject = args[i + 1]; i += 2
            elif args[i] == "--description" and i + 1 < len(args):
                description = args[i + 1]; i += 2
            else:
                i += 1
        result = harness.eval_reply(reply, subject, description)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
