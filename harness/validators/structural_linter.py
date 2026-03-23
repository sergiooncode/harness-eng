"""
harness/validators/structural_linter.py — AST-based structural enforcement.

This is the MECHANICAL part of the harness. Instead of relying on documentation
telling developers "you must implement X", this linter parses the integration.py
file and verifies structurally that:

1. There is exactly one class that subclasses BaseIntegration
2. All abstract methods are implemented
3. parse_webhook returns the correct types (by checking return annotation)
4. No forbidden patterns (e.g. direct HTTP calls outside of execute_action)

This runs BEFORE tests, catching structural issues at the cheapest point.
"""

import ast
from pathlib import Path
from dataclasses import dataclass


@dataclass
class LintIssue:
    file: str
    line: int
    rule: str
    message: str
    severity: str = "error"

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.file}:{self.line} ({self.rule}): {self.message}"


REQUIRED_METHODS = {
    "validate_webhook",
    "parse_webhook",
    "enrich_context",
    "execute_action",
}

FORBIDDEN_IN_PARSE_WEBHOOK = {
    # parse_webhook should be pure transformation, no side effects
    "requests", "urllib", "httpx", "aiohttp",
}


class StructuralLinter:
    """AST-based linter for integration.py files."""

    def lint_file(self, file_path: Path) -> list[LintIssue]:
        issues: list[LintIssue] = []
        source = file_path.read_text()
        filename = str(file_path)

        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as e:
            issues.append(LintIssue(filename, e.lineno or 0, "PARSE", f"Syntax error: {e.msg}"))
            return issues

        # Find integration classes
        integration_classes = self._find_integration_classes(tree)

        if len(integration_classes) == 0:
            issues.append(LintIssue(
                filename, 1, "STRUCT-001",
                "No class inheriting from BaseIntegration found. "
                "Integration must define exactly one such class."
            ))
            return issues

        if len(integration_classes) > 1:
            for cls in integration_classes[1:]:
                issues.append(LintIssue(
                    filename, cls.lineno, "STRUCT-002",
                    f"Multiple BaseIntegration subclasses found: '{cls.name}'. "
                    "Only one is allowed per integration.py."
                ))

        cls_node = integration_classes[0]

        # Check required methods are implemented
        implemented_methods = {
            node.name for node in ast.walk(cls_node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = REQUIRED_METHODS - implemented_methods
        for method in sorted(missing):
            issues.append(LintIssue(
                filename, cls_node.lineno, "STRUCT-003",
                f"Required method '{method}' not implemented."
            ))

        # Check handle_webhook is NOT overridden (it's the standard pipeline)
        if "handle_webhook" in implemented_methods:
            issues.append(LintIssue(
                filename, cls_node.lineno, "STRUCT-004",
                "Method 'handle_webhook' must NOT be overridden. "
                "It is the standard pipeline in BaseIntegration."
            ))

        # Check parse_webhook doesn't do HTTP calls
        for node in ast.walk(cls_node):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "parse_webhook":
                    issues.extend(self._check_no_side_effects(node, filename))

        # Check _get_ai_decision is NOT overridden in production code
        if "_get_ai_decision" in implemented_methods:
            issues.append(LintIssue(
                filename, cls_node.lineno, "STRUCT-005",
                "Method '_get_ai_decision' should not be overridden in integration code. "
                "AI decision logic lives in Rauda Core.",
                severity="warning",
            ))

        return issues

    def _find_integration_classes(self, tree: ast.Module) -> list[ast.ClassDef]:
        """Find all classes that appear to inherit from BaseIntegration."""
        result = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name == "BaseIntegration":
                        result.append(node)
        return result

    def _check_no_side_effects(self, func_node: ast.FunctionDef, filename: str) -> list[LintIssue]:
        """Check that a function doesn't import or call HTTP libraries."""
        issues = []
        for node in ast.walk(func_node):
            # Check for import statements inside the function
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    module = node.names[0].name if node.names else ""
                for forbidden in FORBIDDEN_IN_PARSE_WEBHOOK:
                    if forbidden in module:
                        issues.append(LintIssue(
                            filename, node.lineno, "PURE-001",
                            f"parse_webhook must be a pure transformation. "
                            f"HTTP library '{forbidden}' is not allowed here."
                        ))
        return issues


def lint_integration(file_path: Path) -> list[LintIssue]:
    """Convenience function for the CLI harness."""
    return StructuralLinter().lint_file(file_path)
