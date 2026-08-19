"""API key generation/verification (bcrypt) and Clerk JWT verification.

Only the bcrypt hash of an API key is stored - the raw key is shown to the
user exactly once at creation and cannot be recovered afterwards.
"""
from __future__ import annotations
import secrets

import bcrypt

API_KEY_PREFIX = "aeo_"


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(api_key.encode(), stored_hash.encode())
    except (ValueError, TypeError):
        return False