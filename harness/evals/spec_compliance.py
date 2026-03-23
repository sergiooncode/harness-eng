"""
harness/evals/spec_compliance.py — Verify implementation against challenge spec.

This is NOT about evaluating Rauda's end-user replies. This verifies that
the code the AI agent produced actually satisfies the challenge specification.

Two evaluation layers:
  1. Deterministic checks — file existence, required patterns, structural rules.
     These run ALWAYS, with zero external dependencies.
  2. LLM-based scoring — sends spec + code to Claude for intent verification.
     Runs only when ANTHROPIC_API_KEY is set. Enhances but never replaces layer 1.

Usage:
    python -m harness.harness eval --spec "path/to/spec.md" --target "path/to/code/"
"""

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any


class SpecComplianceEvaluator:
    """Evaluates whether an implementation satisfies a challenge specification."""

    def __init__(self, api_key_env_var: str = "ANTHROPIC_API_KEY", model: str = "claude-sonnet-4-6"):
        self.api_key = os.environ.get(api_key_env_var, "")
        self.model = model

    def evaluate(self, spec: str, code_files: dict[str, str]) -> dict[str, Any]:
        """Compare implementation against spec using deterministic + optional LLM checks.

        Args:
            spec: The challenge specification text
            code_files: Dict of {filepath: file_contents} for all implementation files

        Returns:
            Structured JSON the agent can parse and act on
        """
        # Layer 1: Deterministic checks (always run)
        deterministic = self._deterministic_checks(spec, code_files)

        # Layer 2: LLM-based checks (optional enhancement)
        llm_result = None
        if self.api_key:
            code_block = self._format_code_files(code_files)
            prompt = self._build_prompt(spec, code_block)
            try:
                raw = self._call_llm(prompt)
                llm_result = self._parse_response(raw)
            except Exception as e:
                llm_result = {
                    "passed": None,
                    "error": f"LLM eval failed: {e}",
                    "requirements": [],
                    "next_steps": [f"LLM eval error (non-fatal): {e}"],
                }

        return self._merge_results(deterministic, llm_result)

    def evaluate_from_paths(self, spec_path: Path, target_dir: Path) -> dict[str, Any]:
        """Convenience: load spec and code from filesystem."""
        spec_path = Path(spec_path)
        target_dir = Path(target_dir)

        if not spec_path.exists():
            return {
                "passed": False,
                "error": f"Spec file not found: {spec_path}",
                "checks": {},
                "next_steps": [f"Create spec file at {spec_path}"],
            }

        spec = spec_path.read_text()

        code_files = {}
        if target_dir.is_file():
            code_files[str(target_dir)] = target_dir.read_text()
        elif target_dir.is_dir():
            skip_dirs = {".venv", "venv", ".git", "__pycache__", "node_modules", ".tox", ".eggs"}
            for f in sorted(target_dir.rglob("*")):
                if any(part in skip_dirs for part in f.parts):
                    continue
                if f.is_file() and f.suffix in (".py", ".yaml", ".yml", ".md", ".json"):
                    code_files[str(f.relative_to(target_dir))] = f.read_text()

        if not code_files:
            return {
                "passed": False,
                "error": f"No code files found in {target_dir}",
                "checks": {},
                "next_steps": [f"Add implementation files to {target_dir}"],
            }

        return self.evaluate(spec, code_files)

    # ------------------------------------------------------------------
    # Layer 1: Deterministic checks
    # ------------------------------------------------------------------

    def _deterministic_checks(self, spec: str, code_files: dict[str, str]) -> dict[str, Any]:
        """Extract requirements from spec and verify deterministically."""
        checks = []

        # Check 1: Spec mentions specific files that should exist
        checks.extend(self._check_required_files(spec, code_files))

        # Check 2: Spec mentions specific classes/functions that should be defined
        checks.extend(self._check_required_definitions(spec, code_files))

        # Check 3: Spec mentions patterns that must NOT appear (forbidden patterns)
        checks.extend(self._check_forbidden_patterns(spec, code_files))

        # Check 4: Spec mentions specific strings/keywords that must appear in code
        checks.extend(self._check_required_keywords(spec, code_files))

        # Check 5: No stub/placeholder/TODO left in implementation
        checks.extend(self._check_no_stubs(code_files))

        all_passed = all(c["satisfied"] for c in checks)

        return {
            "passed": all_passed,
            "layer": "deterministic",
            "requirements": checks,
            "summary": (
                "All deterministic checks passed." if all_passed
                else f"{sum(1 for c in checks if not c['satisfied'])}/{len(checks)} checks failed."
            ),
            "next_steps": [c["fix_hint"] for c in checks if not c["satisfied"] and c.get("fix_hint")],
        }

    def _check_required_files(self, spec: str, code_files: dict[str, str]) -> list[dict]:
        """If the spec mentions filenames like 'config.yaml' or 'integration.py', check they exist."""
        checks = []
        # Look for file references in the spec
        file_patterns = re.findall(
            r'(?:create|implement|add|write|need|require|must have)\s+.*?'
            r'[`\'"]([\w./]+\.(?:py|yaml|yml|json|md))[`\'"]',
            spec, re.IGNORECASE,
        )
        # Also look for backtick-quoted filenames
        file_patterns.extend(re.findall(r'`([\w./]+\.(?:py|yaml|yml|json|md))`', spec))
        seen = set()
        for fp in file_patterns:
            basename = fp.split("/")[-1]
            if basename in seen:
                continue
            seen.add(basename)
            found = any(basename in cf for cf in code_files)
            checks.append({
                "requirement": f"File '{basename}' should exist",
                "satisfied": found,
                "evidence": f"Found in: {[cf for cf in code_files if basename in cf]}" if found else "Not found",
                "fix_hint": f"Create file '{basename}' as described in the spec." if not found else "",
            })
        return checks

    def _check_required_definitions(self, spec: str, code_files: dict[str, str]) -> list[dict]:
        """If the spec mentions class or function names, check they're defined."""
        checks = []
        # Look for class references
        class_refs = re.findall(r'(?:class|subclass|inherit|implement)\s+[`\'"]?(\w+Integration|BaseIntegration)\b', spec, re.IGNORECASE)
        # Look for method references
        method_refs = re.findall(r'(?:method|function|implement|define)\s+[`\'"]?(\w+)\([`\'"]?', spec, re.IGNORECASE)

        all_code = "\n".join(code_files.values())

        for cls_name in set(class_refs):
            if cls_name == "BaseIntegration":
                continue  # Framework class, not user-defined
            found = re.search(rf'class\s+{re.escape(cls_name)}\b', all_code)
            checks.append({
                "requirement": f"Class '{cls_name}' should be defined",
                "satisfied": found is not None,
                "evidence": f"Found class definition" if found else "Not found in any file",
                "fix_hint": f"Define class '{cls_name}' that subclasses BaseIntegration." if not found else "",
            })

        for method_name in set(method_refs):
            found = re.search(rf'def\s+{re.escape(method_name)}\b', all_code)
            checks.append({
                "requirement": f"Method '{method_name}' should be defined",
                "satisfied": found is not None,
                "evidence": f"Found method definition" if found else "Not found in any file",
                "fix_hint": f"Implement method '{method_name}()' in your integration class." if not found else "",
            })

        return checks

    def _check_forbidden_patterns(self, spec: str, code_files: dict[str, str]) -> list[dict]:
        """If spec says 'do not', 'must not', 'never', check those patterns are absent."""
        checks = []
        forbidden_phrases = re.findall(
            r'(?:do\s+not|must\s+not|never|forbidden|prohibited|shall\s+not)\s+(.{10,80}?)(?:\.|$)',
            spec, re.IGNORECASE,
        )
        all_code = "\n".join(code_files.values())

        for phrase in forbidden_phrases:
            # Extract key concept from the forbidden phrase
            keywords = re.findall(r'\b\w{4,}\b', phrase.lower())
            # Check if ANY implementation file directly violates
            # (this is a heuristic — the LLM layer does deeper analysis)
            violation_found = False
            violation_evidence = ""
            for kw in keywords[:3]:
                if kw in ("override", "overridden"):
                    if re.search(r'def\s+handle_webhook\b', all_code):
                        violation_found = True
                        violation_evidence = f"Found 'handle_webhook' override"
                        break
            checks.append({
                "requirement": f"Forbidden: {phrase.strip()[:80]}",
                "satisfied": not violation_found,
                "evidence": violation_evidence if violation_found else "No violation detected",
                "fix_hint": f"Remove or fix: {phrase.strip()[:80]}" if violation_found else "",
            })

        return checks

    def _check_required_keywords(self, spec: str, code_files: dict[str, str]) -> list[dict]:
        """Check that specific domain keywords from the spec appear in code."""
        checks = []
        all_code = "\n".join(code_files.values())

        # Look for 'must include', 'must have', 'must contain', 'must implement' phrases
        required_phrases = re.findall(
            r'must\s+(?:include|have|contain|implement|support|provide)\s+(.{5,60}?)(?:\.|,|$)',
            spec, re.IGNORECASE,
        )
        for phrase in required_phrases:
            keywords = [w for w in re.findall(r'\b\w{4,}\b', phrase.lower())
                        if w not in ("must", "have", "that", "this", "with", "from", "each", "every")]
            if not keywords:
                continue
            found = any(kw in all_code.lower() for kw in keywords)
            checks.append({
                "requirement": f"Must include: {phrase.strip()[:60]}",
                "satisfied": found,
                "evidence": f"Keywords {keywords[:3]} found in code" if found else f"Keywords {keywords[:3]} not found",
                "fix_hint": f"Implementation should address: '{phrase.strip()[:60]}'" if not found else "",
            })

        return checks

    def _check_no_stubs(self, code_files: dict[str, str]) -> list[dict]:
        """Check that implementation files don't contain stub/placeholder markers.

        Only flags markers that indicate unfinished implementation — not descriptive
        strings like 'stub — would fetch from ...' that explain production behavior.
        Skips its own source file to avoid self-referential false positives.
        """
        checks = []
        # Build patterns dynamically to avoid self-referential matches.
        # Only match markers in comments (# ...) or raise statements — not inside
        # string literals used as error messages.
        _comment_markers = [
            ("TO" + "DO", "TO" + "DO"),
            ("FIX" + "ME", "FIX" + "ME"),
            ("HA" + "CK", "HA" + "CK"),
        ]
        _raise_marker = ("NotImplemented" + "Error", r'raise\s+NotImplemented' + r'Error')

        for filepath, content in code_files.items():
            if not filepath.endswith(".py"):
                continue
            # Skip this evaluator's own source
            if "spec_compliance" in filepath:
                continue

            content_lines = content.split("\n")

            # Check comment-only markers (only match in # comment lines)
            for label, keyword in _comment_markers:
                hit_lines = []
                for i, line in enumerate(content_lines, 1):
                    stripped = line.lstrip()
                    if stripped.startswith("#") and keyword in stripped:
                        hit_lines.append(i)
                if hit_lines:
                    checks.append({
                        "requirement": f"No '{label}' markers in {filepath}",
                        "satisfied": False,
                        "evidence": f"Found '{label}' in comments at line(s) {hit_lines[:3]} in {filepath}",
                        "fix_hint": f"Replace the {label} at {filepath}:{hit_lines[0]} with a real implementation.",
                    })

            # Check raise NotImplementedError (always a stub indicator)
            label, pattern = _raise_marker
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            if matches:
                lines = []
                for m in matches[:3]:
                    line_num = content[:m.start()].count("\n") + 1
                    lines.append(line_num)
                    checks.append({
                        "requirement": f"No '{label}' markers in {filepath}",
                        "satisfied": False,
                        "evidence": f"Found '{label}' at line(s) {lines} in {filepath}",
                        "fix_hint": f"Replace the {label} at {filepath}:{lines[0]} with a real implementation.",
                    })
        return checks

    # ------------------------------------------------------------------
    # Layer 2: LLM-based checks
    # ------------------------------------------------------------------

    def _format_code_files(self, code_files: dict[str, str]) -> str:
        parts = []
        for filepath, content in code_files.items():
            parts.append(f"=== {filepath} ===\n{content}")
        return "\n\n".join(parts)

    def _build_prompt(self, spec: str, code_block: str) -> str:
        return f"""You are an engineering eval system. Your job is to verify whether an implementation satisfies a challenge specification.

<specification>
{spec}
</specification>

<implementation>
{code_block}
</implementation>

Evaluate the implementation against EVERY requirement in the specification.

Respond with ONLY valid JSON (no markdown, no backticks, no preamble) in this exact format:
{{
  "passed": true/false,
  "overall_score": 0.0 to 1.0,
  "requirements": [
    {{
      "requirement": "brief description of what the spec asks for",
      "satisfied": true/false,
      "evidence": "what in the code satisfies or fails this requirement",
      "fix_hint": "if not satisfied, exactly what the agent should do to fix it"
    }}
  ],
  "summary": "one sentence overall assessment",
  "next_steps": ["list of specific fixes needed, empty if passed"]
}}

Be strict. Only mark a requirement as satisfied if the code clearly implements it.
If something is stubbed or placeholder, mark it as NOT satisfied."""

    def _call_llm(self, prompt: str) -> str:
        """Call Anthropic API using stdlib urllib."""
        payload = json.dumps({
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        for block in body.get("content", []):
            if block.get("type") == "text":
                return block["text"]

        return ""

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Parse LLM response into structured result."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "passed": False,
                "error": "LLM returned unparseable response",
                "raw_response": raw[:500],
                "requirements": [],
                "next_steps": ["Re-run eval — LLM response was malformed"],
            }

        return {
            "passed": result.get("passed", False),
            "overall_score": result.get("overall_score", 0.0),
            "requirements": result.get("requirements", []),
            "summary": result.get("summary", ""),
            "next_steps": result.get("next_steps", []),
        }

    # ------------------------------------------------------------------
    # Result merging
    # ------------------------------------------------------------------

    def _merge_results(self, deterministic: dict, llm_result: dict | None) -> dict[str, Any]:
        """Merge deterministic and LLM results into a single output."""
        if llm_result is None:
            # No API key — deterministic only
            deterministic["llm_eval"] = "skipped (no ANTHROPIC_API_KEY)"
            return deterministic

        if "error" in llm_result:
            # LLM failed — deterministic result stands, note the error
            deterministic["llm_eval"] = llm_result["error"]
            return deterministic

        # Both layers available — merge
        all_requirements = deterministic.get("requirements", []) + llm_result.get("requirements", [])
        all_next_steps = deterministic.get("next_steps", []) + llm_result.get("next_steps", [])
        # Deduplicate next_steps
        seen = set()
        unique_steps = []
        for step in all_next_steps:
            if step not in seen:
                seen.add(step)
                unique_steps.append(step)

        det_passed = deterministic.get("passed", False)
        llm_passed = llm_result.get("passed", False)

        return {
            "passed": det_passed and llm_passed,
            "overall_score": llm_result.get("overall_score", 0.0),
            "layers": {
                "deterministic": {"passed": det_passed, "summary": deterministic.get("summary", "")},
                "llm": {"passed": llm_passed, "summary": llm_result.get("summary", "")},
            },
            "requirements": all_requirements,
            "summary": llm_result.get("summary", deterministic.get("summary", "")),
            "next_steps": unique_steps,
        }
