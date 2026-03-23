"""
harness/eval/reply_eval.py — Evaluation framework for AI-generated replies.

Provides deterministic and LLM-based evaluation of replies before they're sent.
The eval pipeline:
  1. Deterministic checks (length, tone, forbidden content)
  2. LLM-based scoring (relevance, helpfulness, accuracy) — stub
  3. Airtable logging for human review
"""

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class EvalResult:
    """Result of evaluating a single reply."""
    reply_text: str
    passed: bool
    overall_score: float  # 0.0 to 1.0
    checks: dict[str, "CheckResult"] = field(default_factory=dict)
    
    @property
    def failed_checks(self) -> list[str]:
        return [name for name, check in self.checks.items() if not check.passed]


@dataclass
class CheckResult:
    name: str
    passed: bool
    score: float
    message: str = ""


class ReplyEvaluator:
    """Evaluates AI-generated replies with deterministic + LLM-based checks."""

    def __init__(self, quality_threshold: float = 0.7):
        self.quality_threshold = quality_threshold

    def evaluate(self, reply_text: str, ticket_subject: str = "", ticket_description: str = "") -> EvalResult:
        """Run all evaluation checks on a reply."""
        checks = {}

        # Deterministic checks
        checks["not_empty"] = self._check_not_empty(reply_text)
        checks["reasonable_length"] = self._check_length(reply_text)
        checks["no_placeholder"] = self._check_no_placeholders(reply_text)
        checks["no_internal_refs"] = self._check_no_internal_references(reply_text)
        checks["has_greeting"] = self._check_greeting(reply_text)

        # LLM-based checks (stubs — implement during challenge if needed)
        checks["relevance"] = self._check_relevance_stub(reply_text, ticket_subject, ticket_description)

        # Calculate overall score
        scores = [c.score for c in checks.values()]
        overall = sum(scores) / len(scores) if scores else 0.0
        passed = overall >= self.quality_threshold and all(
            c.passed for c in checks.values() if c.name in ("not_empty", "no_placeholder")
        )

        return EvalResult(
            reply_text=reply_text,
            passed=passed,
            overall_score=overall,
            checks=checks,
        )

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------

    def _check_not_empty(self, text: str) -> CheckResult:
        passed = len(text.strip()) > 0
        return CheckResult("not_empty", passed, 1.0 if passed else 0.0,
                           "" if passed else "Reply is empty")

    def _check_length(self, text: str, min_chars: int = 20, max_chars: int = 5000) -> CheckResult:
        length = len(text.strip())
        if length < min_chars:
            return CheckResult("reasonable_length", False, 0.2,
                               f"Reply too short ({length} chars, min {min_chars})")
        if length > max_chars:
            return CheckResult("reasonable_length", False, 0.5,
                               f"Reply too long ({length} chars, max {max_chars})")
        return CheckResult("reasonable_length", True, 1.0)

    def _check_no_placeholders(self, text: str) -> CheckResult:
        placeholders = re.findall(r'\[.*?\]|\{.*?\}|<.*?>', text)
        # Filter out common non-placeholder patterns
        suspicious = [p for p in placeholders if any(kw in p.lower() for kw in
                      ("insert", "name", "placeholder", "todo", "fill", "your", "xxx"))]
        passed = len(suspicious) == 0
        return CheckResult("no_placeholder", passed, 1.0 if passed else 0.0,
                           f"Found placeholders: {suspicious}" if not passed else "")

    def _check_no_internal_references(self, text: str) -> CheckResult:
        """Ensure reply doesn't leak internal Rauda references to end users."""
        internal_patterns = [
            r'\brauda\b', r'\binternal\s+ticket\b', r'\bjira\b',
            r'\bairtable\b', r'\bslack\b',
        ]
        found = []
        for pattern in internal_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append(pattern)
        passed = len(found) == 0
        return CheckResult("no_internal_refs", passed, 1.0 if passed else 0.3,
                           f"Internal references found matching: {found}" if not passed else "")

    def _check_greeting(self, text: str) -> CheckResult:
        greeting_patterns = [
            r'^(hi|hello|hey|dear|good\s+(morning|afternoon|evening))',
            r'^thank',
        ]
        has_greeting = any(re.search(p, text.strip(), re.IGNORECASE) for p in greeting_patterns)
        return CheckResult("has_greeting", True, 1.0 if has_greeting else 0.6,
                           "" if has_greeting else "Consider adding a greeting")

    # ------------------------------------------------------------------
    # LLM-based checks (stubs)
    # ------------------------------------------------------------------

    def _check_relevance_stub(self, reply: str, subject: str, description: str) -> CheckResult:
        """Stub for LLM-based relevance check. Replace with actual LLM call."""
        # In production: send reply + ticket to LLM, ask "is this reply relevant?"
        return CheckResult("relevance", True, 0.8,
                           "Stub — LLM relevance check not connected")
