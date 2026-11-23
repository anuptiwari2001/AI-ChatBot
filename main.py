"""
FastAPI version of the Personal AI Assistant (Groq)
"""

import os
import logging
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

# -----------------------
# Setup
# -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError(
        "GROQ_API_KEY not found. Create a .env file and add your key from https://console.groq.com/keys"
    )

client = Groq(api_key=api_key)

# Change model here if you want
MODEL = "llama-3.1-8b-instant"          # fast
# MODEL = "llama-3.3-70b-versatile"     # smarter

SYSTEM_PROMPT = """You are a helpful, friendly, and capable personal AI assistant.
You answer clearly and concisely. You remember the conversation context.
Be proactive when it helps the user, and ask clarifying questions when needed.
"""

# Simple in-memory conversation history (resets when server restarts)
messages: List[Dict[str, str]] = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

MAX_HISTORY = 20   # system + last N messages

# -----------------------
# FastAPI App
# -----------------------
app = FastAPI(
    title="Personal AI Assistant",
    description="Conversational chatbot powered by Groq",
    version="1.0.0"
)

# Allow React frontend and local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # open for local development; tighten in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    model: str


class HistoryResponse(BaseModel):
    messages: List[Dict[str, str]]


@app.get("/")
def home():
    return {
        "message": "Personal AI Assistant is running!",
        "docs": "http://127.0.0.1:8000/docs",
        "chat": "POST /chat  (use /docs to test easily)",
        "model": MODEL
    }


@app.get("/chat")
def chat_get():
    """Helpful message when someone opens /chat in the browser"""
    return {
        "error": "This endpoint only accepts POST requests.",
        "how_to_use": "Go to http://127.0.0.1:8000/docs and use the /chat endpoint from there.",
        "example_body": {
            "message": "Hello, who are you?"
        }
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Send a message and get the assistant's reply"""
    global messages

    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        # Add user message
        messages.append({"role": "user", "content": user_message})

        # Trim history to avoid context overflow
        if len(messages) > MAX_HISTORY + 1:
            messages = [messages[0]] + messages[-MAX_HISTORY:]

        # Call Groq
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )

        assistant_reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": assistant_reply})

        return ChatResponse(reply=assistant_reply, model=MODEL)

    except Exception as e:
        logging.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history", response_model=HistoryResponse)
def get_history():
    """Get current conversation history"""
    return HistoryResponse(messages=messages)


@app.delete("/history")
def clear_history():
    """Clear conversation history (keeps system prompt)"""
    global messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    return {"message": "Conversation history cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
