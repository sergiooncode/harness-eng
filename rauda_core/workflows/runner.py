"""Workflow runner.

Loads a workflow from YAML, builds the step list, and executes them
sequentially with a shared context dict.
"""

import logging
from pathlib import Path
from typing import Any, Callable

import yaml

from rauda_core.interfaces.workflow import BaseStep
from rauda_core.workflows.llm_step import LlmStep
from rauda_core.workflows.code_step import CodeStep

logger = logging.getLogger(__name__)

# Built-in step types. New types register here.
STEP_TYPES: dict[str, type[BaseStep]] = {
    "llm": LlmStep,
    "code": CodeStep,
}


def load_workflow(
    path: Path,
    functions: dict[str, Callable[..., Any]] | None = None,
) -> list[BaseStep]:
    """Load a workflow YAML and build the step list.

    Args:
        path: Path to the workflow YAML file.
        functions: Dict of callable functions available to code steps.

    Returns:
        Ordered list of BaseStep instances.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    steps: list[BaseStep] = []
    for step_data in data.get("steps", []):
        step_type = step_data["type"]
        step_name = step_data["name"]

        cls = STEP_TYPES.get(step_type)
        if cls is None:
            raise ValueError(
                f"Unknown step type '{step_type}' in step '{step_name}'. "
                f"Valid types: {sorted(STEP_TYPES.keys())}"
            )

        if cls is CodeStep:
            step = cls(name=step_name, config=step_data, functions=functions or {})
        else:
            step = cls(name=step_name, config=step_data)

        steps.append(step)

    return steps


class WorkflowRunner:
    """Executes a linear workflow: each step reads from and writes to a shared context."""

    def run(self, steps: list[BaseStep], initial_context: dict[str, Any]) -> dict[str, Any]:
        """Execute steps in order, accumulating results in context.

        Args:
            steps: Ordered list of workflow steps.
            initial_context: Starting context (e.g. ticket data).

        Returns:
            Final context dict after all steps have run.
        """
        context = dict(initial_context)
        for step in steps:
            logger.info("Running step '%s' (%s)", step.name, type(step).__name__)
            result = step.execute(context)
            context.update(result)
            logger.info("Step '%s' produced keys: %s", step.name, list(result.keys()))
        return context
