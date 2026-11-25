# Personal AI Assistant – React + FastAPI + Groq

ChatGPT-style chat UI on a FastAPI backend that calls the Groq API (streaming replies, per-browser conversation memory).

## 1. Backend

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env          # macOS/Linux: cp .env.example .env
# edit .env -> GROQ_API_KEY=gsk_...   (free key: https://console.groq.com/keys)

uvicorn main:app --reload
```

Check it: http://127.0.0.1:8000/health should show `"api_key_configured": true`.
Interactive docs: http://127.0.0.1:8000/docs

## 2. Frontend (pick one)

**Vite + React + TypeScript (main UI, streaming)**
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```
Different backend URL? Set `VITE_API_URL` (e.g. in `frontend/.env`).

**Zero-install version** – serve `frontend/standalone.html`:
```bash
cd frontend
python -m http.server 5500     # open http://127.0.0.1:5500/standalone.html
```

## Models / tuning

`llama-3.1-8b-instant` and `llama-3.3-70b-versatile` were **retired by Groq on 2026-08-16**.
Defaults are now `openai/gpt-oss-20b` (fast) – switch to `openai/gpt-oss-120b` for harder questions.
Everything is configurable in `.env` (see `.env.example`): `GROQ_MODEL`, `REASONING_EFFORT`
(`low`/`medium`/`high`), `TEMPERATURE`, `MAX_TOKENS`, `MAX_HISTORY`, `SYSTEM_PROMPT`, `CORS_ORIGINS`.
Current model list: https://console.groq.com/docs/models

## API

| Method | Endpoint       | Description                                   |
|--------|----------------|-----------------------------------------------|
| POST   | `/chat`        | `{message, session_id?}` → `{reply, model}`   |
| POST   | `/chat/stream` | Same, streamed as Server-Sent Events          |
| GET    | `/history`     | `?session_id=` conversation so far            |
| DELETE | `/history`     | `?session_id=` clear that conversation        |
| GET    | `/health`      | Status, model, whether a key is configured    |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q          # offline – Groq is faked, no key needed
```
