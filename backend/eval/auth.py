"""
eval/auth.py — Obtain a JWT token for the evaluation test account.

Reads credentials from environment variables:
  EVAL_USER_EMAIL
  EVAL_USER_PASSWORD

Login endpoint: POST /api/v2/auth/login
"""

import os
import httpx


class EvalAuthError(Exception):
    pass


async def get_test_token(base_url: str) -> str:
    email = os.environ.get("EVAL_USER_EMAIL")
    password = os.environ.get("EVAL_USER_PASSWORD")

    if not email or not password:
        raise EvalAuthError(
            "Missing EVAL_USER_EMAIL or EVAL_USER_PASSWORD environment variables."
        )

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{base_url}/api/v2/auth/login",
            json={"email": email, "password": password},
        )

    if resp.status_code != 200:
        raise EvalAuthError(
            f"Login failed — HTTP {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    token = data.get("token")
    if not token:
        raise EvalAuthError(f"No token in login response: {list(data.keys())}")

    return token
