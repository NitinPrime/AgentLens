"""Run the golden dataset through the agent and gate the build on the score.

This is the shape of a CI job: pull the dataset from AgentLens, run the agent
locally on every item, let the server score the outputs with the project's
evaluators, then fail the process if the pass rate drops.

PowerShell:
  $env:AGENTLENS_API_KEY = "al_..."
  python examples/evaluate_agent.py --min-pass-rate 0.8

Add --degrade to simulate a bad prompt so you can see the run fail and compare
it against the previous one in the dashboard.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk"))
sys.path.insert(0, str(ROOT / "examples"))

from agentlens import AgentLens, DatasetItem, EvaluationFailed  # noqa: E402
from demo_data import GOLDEN_DATASET, TICKETS, golden_items  # noqa: E402

BY_QUESTION = {ticket["question"]: ticket for ticket in TICKETS}


def make_agent(degrade: bool):
    """Return the function under test.

    The healthy version answers from the ticket playbook. The degraded version
    drops the specific fact and replies with a generic acknowledgement, which is
    exactly the failure mode the graders exist to catch.
    """

    def agent(item: DatasetItem) -> str:
        ticket = BY_QUESTION.get(str(item.input))
        if ticket is None:
            return "I do not have that information."
        if degrade:
            return "Thanks for reaching out. Our team is looking into it."
        return str(ticket["answer"])

    return agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the demo agent against a dataset")
    parser.add_argument("--dataset", default=GOLDEN_DATASET)
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--agent-version", default="v1.5.0")
    parser.add_argument("--prompt-version", default="support-reply-v4")
    parser.add_argument("--degrade", action="store_true", help="Simulate a regressed prompt")
    parser.add_argument("--upload", action="store_true", help="Create or replace the dataset first")
    parser.add_argument("--evaluator", action="append", default=None, help="Evaluator name (repeatable)")
    args = parser.parse_args()

    api_key = os.getenv("AGENTLENS_API_KEY")
    if not api_key:
        raise SystemExit("Set AGENTLENS_API_KEY to a project key (al_...)")

    with AgentLens(
        api_key=api_key, base_url=os.getenv("AGENTLENS_API_URL", "http://localhost:8000")
    ) as lens:
        if args.upload:
            items = lens.upload_dataset(args.dataset, golden_items(), replace=True)
            print(f"Uploaded {len(items)} items to '{args.dataset}'.")

        label = "degraded" if args.degrade else "baseline"
        run = lens.evaluate(
            args.dataset,
            make_agent(args.degrade),
            name=f"{args.dataset} {label} {args.prompt_version}",
            evaluators=args.evaluator,
            agent_name="support-agent",
            agent_version=args.agent_version,
            prompt_version=args.prompt_version,
        )
        print(run)
        if run.error_message:
            raise SystemExit(f"Run failed: {run.error_message}")

        try:
            run.require_pass_rate(args.min_pass_rate)
        except EvaluationFailed as exc:
            print(f"\nQUALITY GATE FAILED: {exc}")
            raise SystemExit(1) from exc

    print(f"\nQuality gate passed at {run.pass_rate:.1%} (minimum {args.min_pass_rate:.1%}).")


if __name__ == "__main__":
    main()
