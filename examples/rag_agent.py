"""A traced retrieval-augmented docs agent.

Shows the span shape AgentLens expects from a RAG pipeline: a RETRIEVAL span
holding the candidate documents, a rerank step, and a generation call. The last
demo question is not answerable from the corpus, so the agent hedges and the
`not_contains` evaluator flags it as a failure worth investigating.

PowerShell:
  $env:AGENTLENS_API_KEY = "al_..."
  python examples/rag_agent.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk"))
sys.path.insert(0, str(ROOT / "examples"))

from agentlens import AgentLens  # noqa: E402
from demo_data import MODELS, RAG_AGENT, RAG_QUESTIONS, retrieve  # noqa: E402

HEDGE = "I could not find that in the Northwind help centre."
MIN_SCORE = 0.2


def answer_question(
    lens: AgentLens,
    question: str,
    *,
    name: str,
    agent_version: str,
    prompt_version: str,
    top_k: int = 3,
) -> str:
    with lens.trace(
        "docs_question",
        agent_name=RAG_AGENT,
        input={"question": question},
        metadata={"case": name, "top_k": top_k},
        agent_version=agent_version,
        prompt_version=prompt_version,
        model_version=MODELS["writer"],
    ) as trace:
        with trace.span(
            "retrieve", type="RETRIEVAL", input={"question": question, "top_k": top_k}
        ) as retrieval:
            time.sleep(0.02)
            docs: list[dict[str, Any]] = retrieve(question, top_k=top_k)
            retrieval.set_output({"hits": [{"id": d["id"], "score": d["score"]} for d in docs]})
            retrieval.set_metadata(index="kb-northwind", embedder=MODELS["embedder"])

        with trace.span("rerank", type="CHAIN", input={"candidates": len(docs)}) as rerank:
            time.sleep(0.01)
            best = docs[0] if docs else None
            rerank.set_output({"top": best["id"] if best else None, "score": best["score"] if best else 0})

        grounded = bool(best) and best["score"] >= MIN_SCORE
        context = "\n".join(f"[{doc['id']}] {doc['text']}" for doc in docs) or "(no documents)"

        with trace.llm_call(
            model=MODELS["writer"],
            provider="openai",
            messages=[
                {"role": "system", "content": f"Answer only from the context. Prompt {prompt_version}."},
                {"role": "user", "content": f"{question}\n\nContext:\n{context}"},
            ],
            input_tokens=260 + 40 * len(docs),
            temperature=0.1,
            name="generate_answer",
        ) as call:
            time.sleep(0.04)
            answer = best["text"] if grounded else HEDGE
            call.set_completion(answer)
            call.set_usage(output_tokens=len(answer.split()) * 2)

        if not grounded:
            trace.event("no_context", {"question": question})

        trace.set_output(answer)
        return answer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the traced demo RAG agent")
    parser.add_argument("--agent-version", default="rag-v0.3.0")
    parser.add_argument("--prompt-version", default="rag-answer-v2")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    api_key = os.getenv("AGENTLENS_API_KEY")
    if not api_key:
        raise SystemExit("Set AGENTLENS_API_KEY to a project key (al_...)")

    with AgentLens(
        api_key=api_key, base_url=os.getenv("AGENTLENS_API_URL", "http://localhost:8000")
    ) as lens:
        for case in RAG_QUESTIONS:
            answer = answer_question(
                lens,
                case["question"],
                name=case["name"],
                agent_version=args.agent_version,
                prompt_version=args.prompt_version,
                top_k=args.top_k,
            )
            grounded = answer != HEDGE
            print(f"  {case['name']}: {'grounded' if grounded else 'hedged'} - {answer[:70]}")

    print(f"\nSent {len(RAG_QUESTIONS)} RAG traces. One hedged answer is expected.")


if __name__ == "__main__":
    main()
