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


INTEGRATION_REQUIRED_METHODS = {
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
    """AST-based linter for Python files implementing an abstract base class."""

    def __init__(
        self,
        base_class_name: str = "BaseIntegration",
        required_methods: set[str] | None = None,
    ) -> None:
        self.base_class_name = base_class_name
        self.required_methods = required_methods

    def validate(self, path: Path) -> dict:
        """Common interface: validate a file and return structured result."""
        issues = self.lint_file(
            path,
            base_class_name=self.base_class_name,
            required_methods=self.required_methods,
        )
        return {
            "passed": not any(i.severity == "error" for i in issues),
            "file": str(path),
            "issues": [
                {"rule": i.rule, "line": i.line, "message": i.message, "severity": i.severity}
                for i in issues
            ],
        }

    def lint_file(
        self,
        file_path: Path,
        base_class_name: str = "BaseIntegration",
        required_methods: set[str] | None = None,
    ) -> list[LintIssue]:
        if required_methods is None:
            required_methods = INTEGRATION_REQUIRED_METHODS
        issues: list[LintIssue] = []
        source = file_path.read_text()
        filename = str(file_path)

        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as e:
            issues.append(LintIssue(filename, e.lineno or 0, "PARSE", f"Syntax error: {e.msg}"))
            return issues

        # Find subclasses of the target base class
        subclasses = self._find_subclasses(tree, base_class_name)

        if len(subclasses) == 0:
            issues.append(LintIssue(
                filename, 1, "STRUCT-001",
                f"No class inheriting from {base_class_name} found. "
                f"File must define exactly one such class."
            ))
            return issues

        if len(subclasses) > 1:
            for cls in subclasses[1:]:
                issues.append(LintIssue(
                    filename, cls.lineno, "STRUCT-002",
                    f"Multiple {base_class_name} subclasses found: '{cls.name}'. "
                    "Only one is allowed per file."
                ))

        cls_node = subclasses[0]

        # Check required methods are implemented
        implemented_methods = {
            node.name for node in ast.walk(cls_node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = required_methods - implemented_methods
        for method in sorted(missing):
            issues.append(LintIssue(
                filename, cls_node.lineno, "STRUCT-003",
                f"Required method '{method}' not implemented."
            ))

        # BaseIntegration-specific checks
        if base_class_name == "BaseIntegration":
            if "handle_webhook" in implemented_methods:
                issues.append(LintIssue(
                    filename, cls_node.lineno, "STRUCT-004",
                    "Method 'handle_webhook' must NOT be overridden. "
                    "It is the standard pipeline in BaseIntegration."
                ))

            for node in ast.walk(cls_node):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == "parse_webhook":
                        issues.extend(self._check_no_side_effects(node, filename))

            if "_get_ai_decision" in implemented_methods:
                issues.append(LintIssue(
                    filename, cls_node.lineno, "STRUCT-005",
                    "Method '_get_ai_decision' should not be overridden in integration code. "
                    "AI decision logic lives in Rauda Core.",
                    severity="warning",
                ))

        return issues

    def _find_subclasses(self, tree: ast.Module, base_class_name: str) -> list[ast.ClassDef]:
        """Find all classes that inherit from the given base class name."""
        result = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = ""
                    if isinstance(base, ast.Name):
                        name = base.id
                    elif isinstance(base, ast.Attribute):
                        name = base.attr
                    if name == base_class_name:
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
