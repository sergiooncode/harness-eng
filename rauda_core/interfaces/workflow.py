"""Abstract base for workflow steps.

Every step in a workflow implements BaseStep. The runner calls execute()
with a shared context dict and merges the result back in.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseStep(ABC):
    """Abstract base class for all workflow steps.

    Subclasses MUST implement execute(). The harness verifies this structurally.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run this step with the shared context.

        Args:
            context: Accumulated key-value pairs from previous steps.

        Returns:
            Dict of new key-value pairs to merge into context.
        """
        ...
