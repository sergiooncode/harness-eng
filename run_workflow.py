"""CLI entry point for running a client workflow.

Usage:
    python run_workflow.py clients/acme_corp/workflow.yaml --ticket "My order hasn't arrived"
    python run_workflow.py clients/acme_corp/workflow.yaml --context '{"ticket": "My order hasn't arrived"}'
"""

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from rauda_core.workflows.runner import WorkflowRunner, load_workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def load_functions(client_dir: Path) -> dict:
    """Load client functions from functions.py if it exists."""
    functions_path = client_dir / "functions.py"
    if not functions_path.exists():
        return {}

    spec = importlib.util.spec_from_file_location("client_functions", functions_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Collect all public callables
    return {
        name: obj
        for name, obj in vars(mod).items()
        if callable(obj) and not name.startswith("_")
    }


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run a client workflow")
    parser.add_argument("workflow", type=Path, help="Path to workflow.yaml")
    parser.add_argument("--ticket", type=str, help="Ticket text to process")
    parser.add_argument("--context", type=str, help="Initial context as JSON")
    args = parser.parse_args()

    # Build initial context
    if args.context:
        initial_context = json.loads(args.context)
    elif args.ticket:
        initial_context = {"ticket": args.ticket}
    else:
        logger.error("Provide --ticket or --context")
        sys.exit(1)

    # Load client functions from the same directory as the workflow
    client_dir = args.workflow.parent
    functions = load_functions(client_dir)
    if functions:
        logger.info("Loaded functions: %s", list(functions.keys()))

    # Load and run
    steps = load_workflow(args.workflow, functions=functions)
    runner = WorkflowRunner()
    result = runner.run(steps, initial_context)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
