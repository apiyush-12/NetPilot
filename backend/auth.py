"""Clerk authentication for NetPilot FastAPI."""

import os

from clerk_backend_api import (
    AuthenticateRequestOptions,
    authenticate_request,
)
from fastapi import HTTPException, Request


def require_user(request: Request) -> str:
    """Verify the Clerk session and return its user ID."""

    state = authenticate_request(
        request,
        AuthenticateRequestOptions(
            secret_key=os.environ["CLERK_SECRET_KEY"],
            authorized_parties=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
            accepts_token=["session_token"],
        ),
    )

    if not state.is_signed_in:
        raise HTTPException(
            status_code=401,
            detail="Valid Clerk session required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return state.payload["sub"]