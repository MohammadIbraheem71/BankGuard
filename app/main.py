"""FastAPI HTTP surface. Owner: Ibraheem.

Routes are exactly the six endpoints listed in CONTRACT.md.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import warnings

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from . import db
from .audit import tool_context
from .auth import authenticate, create_token, get_current_user
from .config import Mode, require_secret_from_env, using_default_secret
from .gateway import handle_message
from .models import ChatRequest, ChatResponse, SecurityEvent, ToolResult, User
from .security import confirmation, events


class LoginRequest(BaseModel):
    """Synthetic username/password pair from the demo login form."""

    username: str
    password: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Make sure the contract schema exists before serving requests."""
    if using_default_secret():
        message = (
            "BankGuard is using the default demo SECRET_KEY; set SECRET_KEY in .env "
            "before any non-demo use."
        )
        if require_secret_from_env():
            raise RuntimeError(message)
        warnings.warn(message, RuntimeWarning, stacklevel=2)
    db.init_db()
    yield


app = FastAPI(title="BankGuard", version="0.1.0", lifespan=lifespan)


@app.post("/login")
def login(credentials: LoginRequest) -> dict[str, str]:
    """POST /login {username,password} -> {token}."""
    user = authenticate(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"token": create_token(user)}


@app.get("/me")
def me(user: User = Depends(get_current_user)) -> User:
    """GET /me (Bearer) -> User."""
    return user


@app.post("/chat")
def chat(
    req: ChatRequest,
    mode: Mode = Mode.baseline,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    """POST /chat?mode=... (Bearer) ChatRequest -> ChatResponse."""
    return handle_message(user, req, mode)


@app.post("/transfers/{id}/confirm")
def confirm_transfer(id: str, user: User = Depends(get_current_user)) -> ToolResult:
    """POST /transfers/{id}/confirm (Bearer) -> ToolResult."""
    with tool_context(user.id, "full"):
        return confirmation.confirm(user, id)


@app.post("/transfers/{id}/cancel")
def cancel_transfer(id: str, user: User = Depends(get_current_user)) -> ToolResult:
    """POST /transfers/{id}/cancel (Bearer) -> ToolResult."""
    return confirmation.cancel(user, id)


@app.get("/events")
def list_events(
    mode: str | None = None,
    limit: int = 200,
    user: User = Depends(get_current_user),
) -> list[SecurityEvent]:
    """GET /events?mode=&limit= -> list[SecurityEvent]."""
    return events.list_events(limit=limit, mode=mode)
