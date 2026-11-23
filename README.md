# ChatGPT Clone – React + FastAPI + Groq

A ChatGPT-style chat UI connected to your **FastAPI + Groq** backend.

---

## Quick start (recommended – no build)

### 1. Backend

```bash
# From project root
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_your_key
# Get a free key: https://console.groq.com/keys

uvicorn main:app --reload
# Server: http://127.0.0.1:8000
```

### 2. Frontend (standalone – zero install)

```bash
cd frontend
# Option A: open the file
#   open index.html   (macOS)  or  double-click index.html

# Option B: serve with Python (avoids some browser CORS quirks with file://)
python -m http.server 5500
# Then open: http://127.0.0.1:5500
```

Chat at **http://127.0.0.1:5500** (or open `frontend/index.html` directly).

---

## Features

- ChatGPT-inspired dark theme
- Sidebar with conversation snippets
- New chat / Clear conversation
- Suggestion chips on empty state
- Typing indicator
- Enter to send · Shift+Enter for newline
- Mobile-responsive sidebar
- Works with your existing Groq-backed `/chat` API

---

## API

| Method | Endpoint   | Description              |
|--------|------------|--------------------------|
| POST   | `/chat`    | Send message → get reply |
| GET    | `/history` | View history             |
| DELETE | `/history` | Clear history            |

To point the UI at a different backend, edit `API_BASE` near the top of `frontend/index.html`.

---

## Vite + TypeScript version (optional)

A full Vite React TypeScript scaffold also lives under `frontend/` (`src/App.tsx`, etc.).

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

If `npm install` is slow in your environment, use the standalone `index.html` above instead.

---

## Change model

In `main.py`:

```python
MODEL = "llama-3.1-8b-instant"       # fast (default)
# MODEL = "llama-3.3-70b-versatile"  # smarter
```
