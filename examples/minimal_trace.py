"""Send a sample AgentLens trace. Requires a project API key.

PowerShell:
  $env:AGENTLENS_API_KEY = "al_..."
  $env:AGENTLENS_API_URL = "http://localhost:8000"
  python examples/minimal_trace.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk"))

from agentlens import AgentLens  # noqa: E402


def main() -> None:
    api_key = os.getenv("AGENTLENS_API_KEY")
    if not api_key:
        raise SystemExit("Set AGENTLENS_API_KEY to a project key (al_...)")

    lens = AgentLens(api_key=api_key, base_url=os.getenv("AGENTLENS_API_URL", "http://localhost:8000"))
    with lens.trace(
        "customer_support_task",
        agent_name="support-agent",
        input={"message": "Where is my order?"},
    ) as trace:
        with trace.span("planning", type="AGENT") as span:
            span.set_output({"steps": ["lookup_order", "reply"]})

        with trace.tool_call("order_lookup", {"order_id": "1234"}) as tool:
            tool.set_output({"status": "shipped", "eta": "tomorrow"})

        with trace.llm_call(
            model="gpt-4o",
            provider="openai",
            messages=[{"role": "user", "content": "Where is my order?"}],
            input_tokens=420,
        ) as call:
            call.set_completion("Your order 1234 ships tomorrow.")
            call.set_usage(output_tokens=18)

        trace.event("completed", {"channel": "email"})
        trace.set_output("Your order 1234 ships tomorrow.")

    print(f"Sent trace {trace.id}")


if __name__ == "__main__":
    main()
