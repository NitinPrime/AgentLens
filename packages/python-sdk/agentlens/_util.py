from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def jsonable(value: Any) -> Any:
    """Best-effort conversion to JSON-safe data.

    Tracing must never crash the agent it is observing, so anything unknown
    degrades to its ``repr`` instead of raising.
    """

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return jsonable(value.value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return jsonable(dump())
        except Exception:
            pass
    return repr(value)
