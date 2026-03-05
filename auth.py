"""
auth.py — JWT authentication helpers for the admin panel.
Credentials are read from environment variables.

Required environment variables (no defaults — app will refuse to start if missing):
  ADMIN_EMAIL      — admin login e-mail
  ADMIN_PASSWORD   — admin login password
  JWT_SECRET       — secret used to sign JWT tokens (use a long random string)
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from fastapi import Cookie, HTTPException, Request, status
from fastapi.responses import RedirectResponse

# ─── Config ──────────────────────────────────────────────────────────────────

def _require_env(name: str) -> str:
    """Returns the value of an env var or aborts startup with a clear error."""
    value = os.environ.get(name)
    if not value:
        print(f"[FATAL] Environment variable '{name}' is required but not set. Aborting.", file=sys.stderr)
        sys.exit(1)
    return value


ADMIN_EMAIL: str = _require_env("ADMIN_EMAIL")
ADMIN_PASSWORD: str = _require_env("ADMIN_PASSWORD")
JWT_SECRET: str = _require_env("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 4   # Reduced from 24h — shorter window limits exposure if a token is stolen
COOKIE_NAME = "revendai_token"

# ─── Token helpers ────────────────────────────────────────────────────────────


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def authenticate_user(email: str, password: str) -> bool:
    return email == ADMIN_EMAIL and password == ADMIN_PASSWORD


# ─── FastAPI dependencies ─────────────────────────────────────────────────────


def get_token_from_request(request: Request) -> Optional[str]:
    """Tries cookie first, then Authorization header."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def require_auth(request: Request) -> dict:
    """
    Dependency for HTML routes — redirects to /login if not authenticated.
    """
    from fastapi.responses import RedirectResponse
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return payload


def require_api_auth(request: Request) -> dict:
    """
    Dependency for JSON API routes — returns 401 if not authenticated.
    """
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
