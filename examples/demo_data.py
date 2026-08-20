"""Shared fixtures for the AgentLens demo agents and the seed script.

Everything here is deterministic and offline: no model provider key is needed
to produce a dashboard that looks like production traffic.
"""

from __future__ import annotations

from typing import Any

SUPPORT_AGENT = "support-agent"
RAG_AGENT = "docs-rag-agent"

GOLDEN_DATASET = "support-golden"

# Each ticket is one realistic support conversation. ``answer`` is the reply a
# correct agent produces; ``keyword`` is the single fact a grader looks for.
TICKETS: list[dict[str, Any]] = [
    {
        "name": "order-status",
        "question": "Where is my order NW-10231?",
        "intent": "order_status",
        "tool": "order_lookup",
        "tool_args": {"order_id": "NW-10231"},
        "tool_result": {"status": "in_transit", "carrier": "DHL", "eta": "2 days"},
        "answer": "Order NW-10231 is in transit with DHL and arrives in 2 days.",
        "keyword": "in transit",
    },
    {
        "name": "refund-window",
        "question": "Can I still return the blender I bought 20 days ago?",
        "intent": "return_policy",
        "tool": "policy_lookup",
        "tool_args": {"topic": "returns"},
        "tool_result": {"window_days": 30, "condition": "unused"},
        "answer": "Yes. Returns are accepted within 30 days if the item is unused.",
        "keyword": "30 days",
    },
    {
        "name": "damaged-item",
        "question": "My package arrived crushed and the mug is broken.",
        "intent": "damage_claim",
        "tool": "claim_create",
        "tool_args": {"reason": "damaged_in_transit"},
        "tool_result": {"claim_id": "CLM-4471", "replacement": True},
        "answer": "I opened claim CLM-4471 and a replacement mug ships today.",
        "keyword": "CLM-4471",
    },
    {
        "name": "invoice-copy",
        "question": "I need a VAT invoice for order NW-9987.",
        "intent": "billing",
        "tool": "invoice_fetch",
        "tool_args": {"order_id": "NW-9987"},
        "tool_result": {"url": "https://files.northwind.test/inv/NW-9987.pdf"},
        "answer": "Here is the VAT invoice for NW-9987: https://files.northwind.test/inv/NW-9987.pdf",
        "keyword": "NW-9987.pdf",
    },
    {
        "name": "cancel-subscription",
        "question": "Please cancel my Prime Care subscription before the next charge.",
        "intent": "subscription",
        "tool": "subscription_cancel",
        "tool_args": {"plan": "prime_care"},
        "tool_result": {"cancelled": True, "effective": "end_of_period"},
        "answer": "Prime Care is cancelled and stays active until the end of the period.",
        "keyword": "end of the period",
    },
    {
        "name": "address-change",
        "question": "Change the delivery address for NW-10402 to 44 Kingsway, London.",
        "intent": "shipping_change",
        "tool": "address_update",
        "tool_args": {"order_id": "NW-10402", "address": "44 Kingsway, London"},
        "tool_result": {"updated": True, "cutoff": "before dispatch"},
        "answer": "The address for NW-10402 is now 44 Kingsway, London.",
        "keyword": "44 Kingsway",
    },
    {
        "name": "discount-code",
        "question": "My code SPRING20 was rejected at checkout.",
        "intent": "promotions",
        "tool": "promo_check",
        "tool_args": {"code": "SPRING20"},
        "tool_result": {"valid": False, "reason": "expired", "expired_on": "2026-04-30"},
        "answer": "SPRING20 expired on 2026-04-30, so checkout rejected it.",
        "keyword": "expired",
    },
    {
        "name": "warranty-length",
        "question": "How long is the warranty on the Northwind kettle?",
        "intent": "warranty",
        "tool": "policy_lookup",
        "tool_args": {"topic": "warranty"},
        "tool_result": {"years": 2, "covers": "manufacturing defects"},
        "answer": "The kettle has a 2 year warranty covering manufacturing defects.",
        "keyword": "2 year",
    },
    {
        "name": "duplicate-charge",
        "question": "I was charged twice for order NW-10120.",
        "intent": "billing",
        "tool": "payment_lookup",
        "tool_args": {"order_id": "NW-10120"},
        "tool_result": {"charges": 2, "refund_issued": True, "amount": "41.90"},
        "answer": "One of the two charges on NW-10120 was refunded: 41.90 is on its way back.",
        "keyword": "refunded",
    },
    {
        "name": "gift-wrap",
        "question": "Can you gift wrap NW-10455 and hide the price?",
        "intent": "order_change",
        "tool": "order_update",
        "tool_args": {"order_id": "NW-10455", "gift_wrap": True},
        "tool_result": {"gift_wrap": True, "receipt": "hidden"},
        "answer": "NW-10455 will be gift wrapped and the receipt price is hidden.",
        "keyword": "gift wrapped",
    },
    {
        "name": "stock-eta",
        "question": "When will the walnut cutting board be back in stock?",
        "intent": "inventory",
        "tool": "inventory_check",
        "tool_args": {"sku": "CB-WALNUT"},
        "tool_result": {"in_stock": False, "restock": "2026-09-02"},
        "answer": "The walnut cutting board is restocked on 2026-09-02.",
        "keyword": "2026-09-02",
    },
    {
        "name": "escalate-human",
        "question": "This is the third time I am writing. I want a human.",
        "intent": "escalation",
        "tool": "escalate",
        "tool_args": {"priority": "high"},
        "tool_result": {"ticket": "ESC-882", "queue": "tier2", "wait": "15 minutes"},
        "answer": "I escalated you to a tier2 specialist as ESC-882, wait time 15 minutes.",
        "keyword": "ESC-882",
    },
]

# Knowledge base for the RAG demo. ``topics`` drives the fake retriever.
KB_DOCS: list[dict[str, Any]] = [
    {
        "id": "kb-returns",
        "title": "Returns and refunds",
        "topics": ["return", "refund", "blender", "unused"],
        "text": "Northwind accepts returns within 30 days of delivery when the item is unused.",
    },
    {
        "id": "kb-shipping",
        "title": "Shipping and tracking",
        "topics": ["order", "shipping", "tracking", "transit", "carrier"],
        "text": "Standard delivery is 2 to 4 working days. DHL handles in transit tracking updates.",
    },
    {
        "id": "kb-warranty",
        "title": "Warranty coverage",
        "topics": ["warranty", "kettle", "defect"],
        "text": "Small appliances carry a 2 year warranty covering manufacturing defects.",
    },
    {
        "id": "kb-billing",
        "title": "Billing and invoices",
        "topics": ["invoice", "vat", "charge", "refund", "payment"],
        "text": "VAT invoices are generated per order and duplicate charges are refunded within 5 days.",
    },
    {
        "id": "kb-subscriptions",
        "title": "Prime Care subscriptions",
        "topics": ["subscription", "prime", "cancel"],
        "text": "Prime Care can be cancelled any time and remains active until the end of the period.",
    },
]

RAG_QUESTIONS: list[dict[str, Any]] = [
    {"name": "rag-returns", "question": "How many days do I have to return an unused blender?"},
    {"name": "rag-shipping", "question": "Which carrier handles in transit tracking?"},
    {"name": "rag-warranty", "question": "What does the kettle warranty cover?"},
    {"name": "rag-billing", "question": "How fast is a duplicate charge refunded?"},
    {"name": "rag-subscription", "question": "When does a cancelled Prime Care plan stop?"},
    # Deliberately unanswerable from the corpus: exercises the hedge path.
    {"name": "rag-unknown", "question": "Do you ship live lobsters to Norway?"},
]

MODELS = {
    "classifier": "gpt-4o-mini",
    "writer": "gpt-4o",
    "embedder": "text-embedding-3-small",
}


def golden_items() -> list[dict[str, Any]]:
    """Dataset payload for the support agent's golden set."""

    return [
        {
            "name": ticket["name"],
            "input": ticket["question"],
            "expected_output": ticket["answer"],
            "metadata": {"intent": ticket["intent"], "keyword": ticket["keyword"]},
        }
        for ticket in TICKETS
    ]


def retrieve(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Keyword retriever standing in for a vector store.

    Scores each document by how many of its topics appear in the question, so
    the corpus behaves predictably and the unanswerable question really does
    come back empty.
    """

    words = {word.strip(".,?!").lower() for word in question.split()}
    scored: list[dict[str, Any]] = []
    for doc in KB_DOCS:
        hits = sum(1 for topic in doc["topics"] if topic in words)
        if hits:
            scored.append({**doc, "score": round(hits / len(doc["topics"]), 3)})
    scored.sort(key=lambda doc: doc["score"], reverse=True)
    return scored[:top_k]
