import re
import secrets


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "workspace"


def unique_slug(value: str) -> str:
    return f"{slugify(value)}-{secrets.token_hex(3)}"
