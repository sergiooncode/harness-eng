"""LLM workflow step.

Sends a prompt to a configured model and stores the response
under the step's output_key in the shared context.
"""

from typing import Any

from openai import OpenAI

from rauda_core.interfaces.workflow import BaseStep


class LlmStep(BaseStep):
    """Workflow step that calls an LLM with a prompt template.

    Config keys:
        model: The model to call (e.g. "gpt-4o").
        prompt_template: A string with {placeholders} filled from context.
        output_key: Key to store the LLM response under.
    """

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Format the prompt from context, call the LLM, return the response."""
        model = self.config["model"]
        template = self.config["prompt_template"]
        output_key = self.config["output_key"]

        prompt = template.format(**context)

        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content or ""

        return {output_key: result}
