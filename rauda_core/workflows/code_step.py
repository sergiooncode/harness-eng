"""Code workflow step.

Calls a Python function registered by the client and stores the result
under the step's output_key in the shared context.
"""

from typing import Any, Callable

from rauda_core.interfaces.workflow import BaseStep


class CodeStep(BaseStep):
    """Workflow step that calls a Python function.

    Config keys:
        function: The callable to invoke.
        input_keys: List of context keys to pass as arguments.
        output_key: Key to store the function's return value under.
    """

    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        functions: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        super().__init__(name, config)
        self.functions = functions or {}

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Look up the function, call it with input_keys from context."""
        func_name = self.config["function"]
        input_keys = self.config.get("input_keys", [])
        output_key = self.config["output_key"]

        func = self.functions.get(func_name)
        if func is None:
            raise ValueError(
                f"Code step '{self.name}' references function '{func_name}' "
                f"but it is not registered. Register it in the functions dict."
            )

        args = {key: context.get(key) for key in input_keys}
        result = func(**args)

        return {output_key: result}
