import { useState, useRef, useEffect, useCallback } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import './index.css'

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function newSessionId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// Each browser keeps its own conversation on the server (survives page reloads).
function loadSessionId(): string {
  try {
    const saved = localStorage.getItem('chat_session')
    if (saved) return saved
    const id = newSessionId()
    localStorage.setItem('chat_session', id)
    return id
  } catch {
    return newSessionId()
  }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const SUGGESTIONS = [
  { title: 'Explain quantum computing', subtitle: 'in simple terms' },
  { title: 'Write a Python function', subtitle: 'to reverse a linked list' },
  { title: 'Help me plan a trip', subtitle: 'to Japan for 10 days' },
  { title: 'Summarize the benefits', subtitle: 'of learning TypeScript' },
]

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [model, setModel] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sessionRef = useRef<string>(loadSessionId())
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then((d) => d.model && setModel(d.model))
      .catch(() => setError(`Cannot reach the backend at ${API_BASE}. Is it running?`))
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading, scrollToBottom])

  useEffect(() => {
    // Auto-resize textarea
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    }
  }, [input])

  const sendMessage = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    setError(null)
    setInput('')
    // user bubble + an empty assistant bubble that fills in as tokens arrive
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }, { role: 'assistant', content: '' }])
    setLoading(true)
    setSidebarOpen(false)

    const controller = new AbortController()
    abortRef.current = controller
    const appendToLast = (token: string) =>
      setMessages((prev) => {
        const copy = prev.slice()
        const last = copy[copy.length - 1]
        copy[copy.length - 1] = { ...last, content: last.content + token }
        return copy
      })
    // On failure drop the empty assistant bubble (and the user bubble if nothing came back).
    const dropEmptyReply = () =>
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last?.role === 'assistant' && last.content === '') return prev.slice(0, -1)
        return prev
      })

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, session_id: sessionRef.current }),
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Request failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''
        for (const evt of events) {
          if (!evt.startsWith('data: ')) continue
          const data = JSON.parse(evt.slice(6))
          if (data.error) throw new Error(data.error)
          if (data.token) appendToLast(data.token)
          if (data.model) setModel(data.model)
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(
        err instanceof TypeError
          ? `Failed to reach the backend at ${API_BASE}. Is it running?`
          : err instanceof Error
            ? err.message
            : 'Something went wrong',
      )
      dropEmptyReply()
    } finally {
      setLoading(false)
      abortRef.current = null
      textareaRef.current?.focus()
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    sendMessage(input)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const clearHistory = async () => {
    abortRef.current?.abort()
    try {
      await fetch(`${API_BASE}/history?session_id=${encodeURIComponent(sessionRef.current)}`, {
        method: 'DELETE',
      })
      setMessages([])
      setError(null)
    } catch {
      setError('Could not clear history')
    }
  }

  const newChat = () => {
    clearHistory()
    setSidebarOpen(false)
  }

  return (
    <div className="app">
      {sidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={newChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
        </div>

        <div className="sidebar-history">
          <div className="history-label">This conversation</div>
          {messages.length === 0 ? (
            <div className="history-item" style={{ cursor: 'default', opacity: 0.5 }}>
              No messages yet
            </div>
          ) : (
            messages
              .filter((m) => m.role === 'user')
              .slice(-8)
              .map((m, i) => (
                <div key={i} className="history-item" title={m.content}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  {m.content.slice(0, 40)}
                  {m.content.length > 40 ? '…' : ''}
                </div>
              ))
          )}
        </div>

        <div className="sidebar-footer">
          <button className="clear-btn" onClick={clearHistory}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Clear conversation
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="main-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <h1>Personal AI Assistant</h1>
          </div>
          <span className="model-badge">{model}</span>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <div className="messages">
          {messages.length === 0 && !loading ? (
            <div className="empty-state">
              <h2>How can I help you today?</h2>
              <p>Powered by Groq · Connected to your FastAPI backend</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.title}
                    className="suggestion"
                    onClick={() => sendMessage(`${s.title} ${s.subtitle}`)}
                  >
                    <strong>{s.title}</strong>
                    {s.subtitle}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages-inner">
              {messages.filter((m) => m.role === 'user' || m.content !== '').map((m, i) => (
                <div key={i} className={`message ${m.role}`}>
                  <div className="message-avatar">
                    {m.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div className="message-content">{m.content}</div>
                </div>
              ))}
              {loading && messages[messages.length - 1]?.content === '' && (
                <div className="message assistant">
                  <div className="message-avatar">AI</div>
                  <div className="message-content">
                    <div className="typing">
                      <span /><span /><span />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="input-area">
          <form className="input-wrapper" onSubmit={handleSubmit}>
            <div className="input-box">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message the assistant…"
                rows={1}
                disabled={loading}
              />
              <button
                type="submit"
                className="send-btn"
                disabled={!input.trim() || loading}
                aria-label="Send message"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </div>
            <p className="input-hint">
              Enter to send · Shift+Enter for new line · Backend at {API_BASE}
            </p>
          </form>
        </div>
      </main>
    </div>
  )
}

export default App
