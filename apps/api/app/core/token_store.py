"""In-memory token backend used when Redis is not configured."""

from datetime import datetime, timedelta, timezone


class MemoryTokenStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, datetime]] = {}

    def _purge_if_expired(self, key: str) -> None:
        item = self._data.get(key)
        if item is None:
            return
        _, expires_at = item
        if datetime.now(timezone.utc) >= expires_at:
            self._data.pop(key, None)

    async def get(self, key: str) -> bytes | None:
        self._purge_if_expired(key)
        item = self._data.get(key)
        if item is None:
            return None
        return item[0]

    async def setex(self, key: str, time: int, value: str | bytes) -> None:
        encoded = value.encode() if isinstance(value, str) else value
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(time))
        self._data[key] = (encoded, expires_at)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def aclose(self) -> None:
        return None
