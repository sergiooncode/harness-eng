"""Abstract base class for result writers."""

from abc import ABC, abstractmethod

from rauda_core.schemas import Evaluation


class ResultWriter(ABC):
    """Interface for writing evaluation results to a destination."""

    @abstractmethod
    def write(
        self,
        rows: list[dict[str, str]],
        evaluations: list[Evaluation | None],
    ) -> None:
        """Write evaluated results to the configured destination.

        Args:
            rows: Original ticket/reply rows.
            evaluations: Evaluation results aligned with rows (None for failures).
        """
