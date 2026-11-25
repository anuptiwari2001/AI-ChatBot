"""Offline tests: the Groq client is faked, so no API key or network is needed.

Run:  pip install pytest && pytest -q
"""
import json
from types import SimpleNamespace as NS

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

import main


def _resp(content, finish="stop"):
    return NS(choices=[NS(message=NS(content=content), finish_reason=finish)])


def _chunk(text):
    return NS(choices=[NS(delta=NS(content=text))])


class FakeCompletions:
    def __init__(self):
        self.calls = []
        self.behaviour = lambda **kw: _resp("hi there")

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.behaviour(**kwargs)


@pytest.fixture()
def api(monkeypatch):
    fake = FakeCompletions()
    monkeypatch.setattr(main, "client", NS(chat=NS(completions=fake)))
    main._sessions.clear()
    return TestClient(main.app), fake


def _status_error(cls, code):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls("boom", response=httpx.Response(code, request=req), body=None)


def test_chat_roundtrip_and_params(api):
    c, fake = api
    r = c.post("/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert r.json() == {"reply": "hi there", "model": main.MODEL}
    kw = fake.calls[0]
    assert kw["model"] == "openai/gpt-oss-20b"
    assert "max_completion_tokens" in kw and "max_tokens" not in kw
    assert kw["reasoning_effort"] == "low" and kw["include_reasoning"] is False
    assert kw["messages"][0]["role"] == "system"


def test_sessions_are_isolated_and_remembered(api):
    c, fake = api
    c.post("/chat", json={"message": "a1", "session_id": "A"})
    c.post("/chat", json={"message": "b1", "session_id": "B"})
    c.post("/chat", json={"message": "a2", "session_id": "A"})
    sent = [m["content"] for m in fake.calls[2]["messages"]]
    assert "a1" in sent and "a2" in sent and "b1" not in sent
    hist = c.get("/history", params={"session_id": "B"}).json()["messages"]
    assert [m["content"] for m in hist[1:]] == ["b1", "hi there"]
    c.delete("/history", params={"session_id": "A"})
    assert len(c.get("/history", params={"session_id": "A"}).json()["messages"]) == 1


def test_failed_call_does_not_pollute_history(api):
    c, fake = api
    fake.behaviour = lambda **kw: (_ for _ in ()).throw(_status_error(groq.RateLimitError, 429))
    assert c.post("/chat", json={"message": "x"}).status_code == 429
    assert len(c.get("/history").json()["messages"]) == 1  # system prompt only


@pytest.mark.parametrize("cls,code,expected", [
    (groq.AuthenticationError, 401, 401),
    (groq.NotFoundError, 404, 502),
])
def test_error_mapping(api, cls, code, expected):
    c, fake = api
    fake.behaviour = lambda **kw: (_ for _ in ()).throw(_status_error(cls, code))
    r = c.post("/chat", json={"message": "x"})
    assert r.status_code == expected and r.json()["detail"]


def test_history_window_never_starts_with_assistant(api):
    c, fake = api
    for i in range(30):
        c.post("/chat", json={"message": f"m{i}"})
    msgs = fake.calls[-1]["messages"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert len(msgs) <= main.MAX_HISTORY + 1


def test_empty_and_whitespace_rejected(api):
    c, _ = api
    assert c.post("/chat", json={"message": "   "}).status_code == 400


def test_missing_key_gives_503(monkeypatch):
    monkeypatch.setattr(main, "client", None)
    assert TestClient(main.app).post("/chat", json={"message": "hi"}).status_code == 503


def test_stream(api):
    c, fake = api
    fake.behaviour = lambda **kw: iter([_chunk("Hel"), NS(choices=[]), _chunk("lo")])
    r = c.post("/chat/stream", json={"message": "hey", "session_id": "S"})
    events = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    assert [e.get("token") for e in events if "token" in e] == ["Hel", "lo"]
    assert events[-1]["done"] is True
    hist = c.get("/history", params={"session_id": "S"}).json()["messages"]
    assert hist[-1] == {"role": "assistant", "content": "Hello"}
