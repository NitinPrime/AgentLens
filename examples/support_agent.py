"""A traced customer support agent you can run against a local AgentLens.

The agent is fully simulated (no model provider needed) but the trace shape
matches a real tool-using agent: intent classification, a tool call that
sometimes retries, a policy check, and a drafted reply.

PowerShell:
  $env:AGENTLENS_API_KEY = "al_..."
  python examples/support_agent.py --runs 12 --agent-version v1.5.0

Pass --break-tools to reproduce a bad deploy: the lookup tool starts timing out
and the traces show up as errors in the dashboard.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk"))
sys.path.insert(0, str(ROOT / "examples"))

from agentlens import AgentLens  # noqa: E402
from demo_data import MODELS, SUPPORT_AGENT, TICKETS  # noqa: E402


class ToolTimeout(RuntimeError):
    """Raised when a downstream tool does not answer in time."""


def _pause(seconds: float) -> None:
    """Sleep so the recorded durations look like real work."""

    time.sleep(max(seconds, 0.0))


def _call_tool(name: str, args: dict[str, Any], result: dict[str, Any], *, fail: bool) -> dict[str, Any]:
    if fail:
        raise ToolTimeout(f"{name} timed out after 3 attempts for {args}")
    return result


def handle_ticket(
    lens: AgentLens,
    ticket: dict[str, Any],
    *,
    agent_version: str,
    prompt_version: str,
    session_id: str,
    latency_scale: float = 1.0,
    fail_tool: bool = False,
    degrade_answer: bool = False,
) -> str | None:
    """Answer one ticket and record the whole thing as a single trace."""

    with lens.trace(
        "support_ticket",
        agent_name=SUPPORT_AGENT,
        session_id=session_id,
        input={"question": ticket["question"]},
        metadata={"intent": ticket["intent"], "channel": "email"},
        agent_version=agent_version,
        prompt_version=prompt_version,
        model_version=MODELS["writer"],
    ) as trace:
        with trace.llm_call(
            model=MODELS["classifier"],
            provider="openai",
            messages=[
                {"role": "system", "content": "Classify the support intent."},
                {"role": "user", "content": ticket["question"]},
            ],
            input_tokens=140,
            temperature=0.0,
            name="classify_intent",
        ) as classify:
            _pause(0.03 * latency_scale)
            classify.set_completion({"intent": ticket["intent"], "confidence": 0.94})
            classify.set_usage(output_tokens=12)

        trace.event("intent_resolved", {"intent": ticket["intent"]})

        # Let the timeout propagate through both spans so the tool call and its
        # parent are both recorded as errors, then handle it at the trace level
        # instead of crashing the batch.
        failure: ToolTimeout | None = None
        try:
            with trace.span("resolve_request", type="AGENT") as work:
                with trace.tool_call(
                    ticket["tool"],
                    ticket["tool_args"],
                    retry_count=3 if fail_tool else 0,
                    metadata={"timeout_ms": 4000},
                ) as tool:
                    _pause(0.05 * latency_scale)
                    tool.set_output(
                        _call_tool(
                            ticket["tool"], ticket["tool_args"], ticket["tool_result"], fail=fail_tool
                        )
                    )
                work.set_output({"resolved": True, "tool": ticket["tool"]})
        except ToolTimeout as exc:
            failure = exc

        if failure is not None:
            trace.event("tool_failed", {"tool": ticket["tool"], "error": str(failure)})
            trace.mark_error(failure)
            return None

        with trace.llm_call(
            model=MODELS["writer"],
            provider="openai",
            messages=[
                {"role": "system", "content": f"Reply to the customer. Prompt {prompt_version}."},
                {"role": "user", "content": ticket["question"]},
                {"role": "tool", "content": str(ticket["tool_result"])},
            ],
            input_tokens=520 if not degrade_answer else 380,
            temperature=0.2,
            name="draft_reply",
        ) as writer:
            _pause(0.06 * latency_scale)
            answer = (
                "Thanks for reaching out. Our team is looking into it."
                if degrade_answer
                else ticket["answer"]
            )
            writer.set_completion(answer)
            writer.set_usage(output_tokens=90 if not degrade_answer else 24)

        trace.set_output(answer)
        trace.event("reply_sent", {"length": len(answer)})
        return answer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the traced demo support agent")
    parser.add_argument("--runs", type=int, default=len(TICKETS))
    parser.add_argument("--agent-version", default="v1.5.0")
    parser.add_argument("--prompt-version", default="support-reply-v4")
    parser.add_argument("--error-rate", type=float, default=0.08)
    parser.add_argument("--latency-scale", type=float, default=1.0)
    parser.add_argument("--break-tools", action="store_true", help="Fail every tool call")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    api_key = os.getenv("AGENTLENS_API_KEY")
    if not api_key:
        raise SystemExit("Set AGENTLENS_API_KEY to a project key (al_...)")

    rng = random.Random(args.seed)
    session_id = f"demo-{rng.randrange(10**6):06d}"
    sent = 0
    failed = 0

    with AgentLens(
        api_key=api_key, base_url=os.getenv("AGENTLENS_API_URL", "http://localhost:8000")
    ) as lens:
        project = lens.verify()
        print(f"Sending to project '{project.get('project_name')}' as {project.get('key_prefix')}...")

        for index in range(args.runs):
            ticket = TICKETS[index % len(TICKETS)]
            fail_tool = args.break_tools or rng.random() < args.error_rate
            answer = handle_ticket(
                lens,
                ticket,
                agent_version=args.agent_version,
                prompt_version=args.prompt_version,
                session_id=session_id,
                latency_scale=args.latency_scale,
                fail_tool=fail_tool,
            )
            sent += 1
            if answer is None:
                failed += 1
            print(f"  [{index + 1}/{args.runs}] {ticket['name']}: {'error' if answer is None else 'ok'}")

    print(f"\nSent {sent} traces ({failed} errors) for {args.agent_version}.")
    print("Open http://localhost:3000/traces to watch them arrive live.")


if __name__ == "__main__":
    main()
