"""FastAPI dependencies for authentication.

Accepts either an API key (X-API-Key header) or a Clerk session token
(Authorization: Bearer ...). API keys are the machine-to-machine path;
Clerk is what the Phase 4 dashboard uses. A verified Clerk login is
provisioned into the users table on first sight - see
repository.get_or_create_user_by_email.
"""
from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api.security import verify_api_key
from autoeval_ops.config import settings
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

logger = logging.getLogger(__name__)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _user_from_api_key(db: AsyncSession, api_key: str) -> User | None:
    # bcrypt hashes are salted, so the key can't be looked up directly -
    # each candidate hash must be checked. Fine at this scale; revisit with
    # a lookup-prefix column if the user table grows large.
    for user in await repository.list_users_with_api_keys(db):
        if user.api_key_hash and verify_api_key(api_key, user.api_key_hash):
            return user
    return None


async def _user_from_clerk_token(db: AsyncSession, token: str) -> User | None:
    if not settings.clerk_jwks_url:
        return None
    from autoeval_ops.api.clerk import ClerkVerifier

    verifier = ClerkVerifier(settings.clerk_jwks_url)
    try:
        claims = await verifier.verify(token)
    except Exception:
        logger.exception("Clerk JWT verification failed")
        return None
    email = claims.get("email")
    if not email:
        return None
    return await repository.get_or_create_user_by_email(db, email)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(default=""),
    authorization: str = Header(default=""),
) -> User:
    if x_api_key:
        user = await _user_from_api_key(db, x_api_key)
        if user:
            return user

    if authorization.startswith("Bearer "):
        user = await _user_from_clerk_token(db, authorization.removeprefix("Bearer "))
        if user:
            return user

    raise _CREDENTIALS_ERROR
