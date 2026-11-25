"""
Personal AI Assistant - FastAPI + Groq

Run:  uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import json
import logging
import os
import threading
from collections import OrderedDict
from typing import Dict, Iterator, List, Optional

import groq
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Config (override any of these in .env)
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
load_dotenv()

# NOTE: llama-3.1-8b-instant and llama-3.3-70b-versatile were shut down on
# 2026-08-16. Current replacements: openai/gpt-oss-20b (fast) and
# openai/gpt-oss-120b (smarter). See https://console.groq.com/docs/models
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.6"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
# gpt-oss models are reasoning models: low = fastest, high = most careful.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))      # messages kept per session (excl. system)
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "200"))   # oldest idle sessions are dropped
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful, friendly and capable personal AI assistant. "
    "Answer clearly and concisely; use Markdown for code blocks and lists. "
    "Use the earlier conversation for context. If a request is ambiguous, "
    "ask one short clarifying question instead of guessing. "
    "If you don't know something, say so rather than making it up.",
)

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logging.warning(
        "GROQ_API_KEY is not set. Copy .env.example to .env and add a key from "
        "https://console.groq.com/keys - /chat will return 503 until then."
    )
client: Optional[Groq] = Groq(api_key=api_key, max_retries=2, timeout=60.0) if api_key else None

# -----------------------------------------------------------------------------
# Per-session conversation memory (in-memory; resets when the server restarts)
# -----------------------------------------------------------------------------
DEFAULT_SESSION = "default"
_sessions: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
_lock = threading.Lock()


def _get_history(session_id: str) -> List[Dict[str, str]]:
    """Return a copy of the session's messages (without the system prompt)."""
    with _lock:
        return list(_sessions.get(session_id, []))


def _save_history(session_id: str, history: List[Dict[str, str]]) -> None:
    with _lock:
        _sessions[session_id] = history[-MAX_HISTORY:]
        _sessions.move_to_end(session_id)
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)


def _build_payload(history: List[Dict[str, str]], user_message: str) -> List[Dict[str, str]]:
    trimmed = (history + [{"role": "user", "content": user_message}])[-MAX_HISTORY:]
    # Never start the window on an assistant turn after trimming.
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)
    return [{"role": "system", "content": SYSTEM_PROMPT}] + trimmed


def _completion_kwargs(stream: bool) -> dict:
    kwargs = dict(
        model=MODEL,
        temperature=TEMPERATURE,
        max_completion_tokens=MAX_TOKENS,
        stream=stream,
    )
    if MODEL.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = REASONING_EFFORT
        kwargs["include_reasoning"] = False   # return only the final answer
    return kwargs


def _to_http_error(exc: Exception) -> HTTPException:
    """Translate Groq SDK errors into clear HTTP errors for the UI."""
    if isinstance(exc, groq.AuthenticationError):
        return HTTPException(401, "Groq rejected the API key. Check GROQ_API_KEY in your .env file.")
    if isinstance(exc, groq.RateLimitError):
        return HTTPException(429, "Groq rate limit reached. Wait a moment and try again.")
    if isinstance(exc, groq.NotFoundError):
        return HTTPException(
            502,
            f"Model '{MODEL}' was not found on Groq (it may be retired). "
            "Set GROQ_MODEL in .env - see https://console.groq.com/docs/models",
        )
    if isinstance(exc, groq.APIConnectionError):
        return HTTPException(502, "Could not reach the Groq API. Check your internet connection.")
    if isinstance(exc, groq.APIStatusError):
        return HTTPException(502, f"Groq API error ({exc.status_code}): {exc.message}")
    return HTTPException(500, f"Unexpected error: {exc}")


def _require_client() -> Groq:
    if client is None:
        raise HTTPException(503, "GROQ_API_KEY is not configured on the server. Add it to .env and restart.")
    return client


# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Personal AI Assistant",
    description="Conversational chatbot powered by Groq",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,     # "*" for local dev; set CORS_ORIGINS in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=8000)
    session_id: str = Field(DEFAULT_SESSION, max_length=64)


class ChatResponse(BaseModel):
    reply: str
    model: str


class HistoryResponse(BaseModel):
    messages: List[Dict[str, str]]


@app.get("/")
def home():
    return {
        "message": "Personal AI Assistant is running!",
        "docs": "/docs",
        "model": MODEL,
        "api_key_configured": client is not None,
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "api_key_configured": client is not None}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Send a message and get the full reply in one response."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(400, "Message cannot be empty")

    groq_client = _require_client()
    history = _get_history(request.session_id)

    try:
        response = groq_client.chat.completions.create(
            messages=_build_payload(history, user_message), **_completion_kwargs(stream=False)
        )
    except HTTPException:
        raise
    except Exception as exc:
        logging.error("Chat error: %s", exc)
        raise _to_http_error(exc)

    choice = response.choices[0]
    reply = (choice.message.content or "").strip()
    if not reply:
        # Reasoning models can spend the whole budget thinking.
        reply = "(The model returned an empty answer - try again or raise MAX_TOKENS in .env.)"
    elif choice.finish_reason == "length":
        reply += "\n\n[reply was cut off - raise MAX_TOKENS in .env for longer answers]"

    # Only persist the turn once it succeeded, so failures don't leave dangling messages.
    history += [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}]
    _save_history(request.session_id, history)
    return ChatResponse(reply=reply, model=MODEL)


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """Same as /chat but streams the answer as Server-Sent Events."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(400, "Message cannot be empty")

    groq_client = _require_client()
    history = _get_history(request.session_id)
    payload = _build_payload(history, user_message)

    def sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    def events() -> Iterator[str]:
        parts: List[str] = []
        try:
            stream = groq_client.chat.completions.create(messages=payload, **_completion_kwargs(stream=True))
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    parts.append(delta)
                    yield sse({"token": delta})
        except Exception as exc:
            logging.error("Stream error: %s", exc)
            yield sse({"error": _to_http_error(exc).detail})
            return

        reply = "".join(parts).strip()
        if reply:
            _save_history(
                request.session_id,
                history + [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}],
            )
        yield sse({"done": True, "model": MODEL})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/history", response_model=HistoryResponse)
def get_history(session_id: str = Query(DEFAULT_SESSION, max_length=64)):
    """Get the conversation history of a session (system prompt included)."""
    return HistoryResponse(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + _get_history(session_id)
    )


@app.delete("/history")
def clear_history(session_id: str = Query(DEFAULT_SESSION, max_length=64)):
    """Clear one session's conversation history."""
    with _lock:
        _sessions.pop(session_id, None)
    return {"message": "Conversation history cleared"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=True)
