import hashlib
import hmac
import secrets

API_KEY_PREFIX = "al_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext_secret, display_prefix, sha256_hash)."""
    secret = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    prefix = secret[:12]
    return secret, prefix, hash_api_key(secret)


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_api_key_hash(secret: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_api_key(secret), hashed)


def looks_like_api_key(token: str) -> bool:
    return token.startswith(API_KEY_PREFIX)
