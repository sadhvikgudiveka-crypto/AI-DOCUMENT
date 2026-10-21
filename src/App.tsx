import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  ArrowUpRight,
  BookOpenText,
  Check,
  ChevronDown,
  CircleHelp,
  FileText,
  FileUp,
  LoaderCircle,
  MessageSquareText,
  Plus,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'

type DocumentInfo = {
  id: string
  name: string
  page_count: number
  chunk_count: number
}

type Citation = {
  id: string
  document: string
  page: number | null
  passage: string
  start: number
}

type Message = {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
  pending?: boolean
}

const starterQuestions = [
  'What are the main ideas?',
  'What should I remember?',
  'Can you summarize this document?',
]

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new Error('The local API is unavailable. Start the FastAPI server and try again.')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || 'Something went wrong. Please try again.')
  }
  return payload as T
}

function App() {
  const [document, setDocument] = useState<DocumentInfo | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [demoMode, setDemoMode] = useState(true)
  const [providerReady, setProviderReady] = useState(true)
  const [maxUploadMb, setMaxUploadMb] = useState(10)
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const questionInput = useRef<HTMLTextAreaElement>(null)
  const endOfChat = useRef<HTMLDivElement>(null)

  useEffect(() => {
    request<{ demo_mode: boolean; configured: boolean; max_upload_mb: number }>('/api/health')
      .then((health) => {
        setDemoMode(health.demo_mode)
        setProviderReady(health.configured)
        setMaxUploadMb(health.max_upload_mb)
      })
      .catch(() => setDemoMode(true))
  }, [])

  useEffect(() => {
    endOfChat.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  async function selectFile(file?: File) {
    if (!file) return
    setError('')
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!['pdf', 'txt'].includes(extension || '')) {
      setError('That file type is not supported. Choose a PDF or .txt file.')
      return
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      setError(`This file is larger than ${maxUploadMb} MB. Choose a smaller document.`)
      return
    }
    setUploading(true)
    setMessages([])
    setActiveCitation(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const uploaded = await request<DocumentInfo>('/api/documents', { method: 'POST', body: form })
      setDocument(uploaded)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not process this document.')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function loadDemo() {
    setError('')
    setUploading(true)
    setMessages([])
    setActiveCitation(null)
    try {
      const sample = await request<DocumentInfo>('/api/demo', { method: 'POST' })
      setDocument(sample)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the sample document.')
    } finally {
      setUploading(false)
    }
  }

  async function removeDocument() {
    if (!document) return
    const id = document.id
    setDocument(null)
    setMessages([])
    setActiveCitation(null)
    setError('')
    try {
      await request(`/api/documents/${id}`, { method: 'DELETE' })
    } catch {
      // The document may already have expired from the in-memory API store.
    }
  }

  async function ask(value = question) {
    const prompt = value.trim()
    if (!document || !prompt || busy) return
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', text: prompt }
    setMessages((current) => [...current, userMessage])
    setQuestion('')
    setError('')
    setBusy(true)
    try {
      const result = await request<{ answer: string; citations: Citation[] }>(
        `/api/documents/${document.id}/questions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: prompt }),
        },
      )
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: result.answer,
        citations: result.citations,
      }])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not get an answer.')
    } finally {
      setBusy(false)
      questionInput.current?.focus()
    }
  }

  function onQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void ask()
    }
  }

  const hasConversation = messages.length > 0

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Marginalia home">
          <span className="brand-mark"><BookOpenText size={18} strokeWidth={1.8} /></span>
          <span>marginalia<span className="brand-period">.</span></span>
        </a>
        <div className="topbar-right">
          <span className={`mode-indicator ${demoMode ? 'is-demo' : ''}`}>
            <span className="status-dot" />
            {demoMode ? 'Demo mode' : providerReady ? 'AI connected' : 'Setup needed'}
          </span>
          <button className="icon-button help-button" type="button" aria-label="About document privacy" title="About document privacy" onClick={() => setError(demoMode ? 'Demo mode processes your document locally in memory and does not save it to disk.' : 'Your document is held in memory by the local backend. Retrieved passages and questions are sent to the configured AI provider; uploads are not saved to disk.')}>
            <CircleHelp size={17} />
          </button>
        </div>
      </header>

      <main className={`workspace ${document ? 'has-document' : ''}`} id="home">
        {!document ? (
          <section className="welcome-view" aria-labelledby="welcome-title">
            <div className="welcome-copy">
              <div className="eyebrow"><Sparkles size={14} /> A clearer read starts here</div>
              <h1 id="welcome-title">Your documents,<br /><em>understood.</em></h1>
              <p className="welcome-description">Bring a document. Ask what matters.<br className="desktop-break" /> Get answers with the page to prove it.</p>
            </div>
            <div
              className={`upload-zone ${dragging ? 'is-dragging' : ''} ${uploading ? 'is-loading' : ''}`}
              onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); void selectFile(event.dataTransfer.files[0]) }}
            >
              <input
                ref={fileInput}
                className="visually-hidden"
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                aria-label="Choose a PDF or text document"
                onChange={(event) => void selectFile(event.target.files?.[0])}
              />
              <div className="upload-icon"><FileUp size={23} strokeWidth={1.7} /></div>
              <h2>{uploading ? 'Reading your document…' : 'Drop a document to begin'}</h2>
              <p>{uploading ? 'Extracting text and preparing your workspace' : `PDF or plain text, up to ${maxUploadMb} MB`}</p>
              {uploading ? (
                <LoaderCircle className="upload-spinner" size={19} aria-label="Processing" />
              ) : (
                <button className="primary-button" type="button" onClick={() => fileInput.current?.click()}>
                  <Plus size={17} /> Choose a file
                </button>
              )}
              <div className="privacy-note"><ShieldCheck size={14} />{demoMode ? 'Local demo; documents stay in memory' : 'Passages sent to configured AI provider'}</div>
            </div>
            {error && <div className="error-message welcome-error" role="alert"><CircleHelp size={16} /><span>{error}</span><button type="button" aria-label="Dismiss message" onClick={() => setError('')}><X size={15} /></button></div>}
            <div className="welcome-bottom">
              <span>Or take a quick look around</span>
              <button className="text-button" type="button" onClick={() => void loadDemo()} disabled={uploading}>
                Try the sample document <ArrowUpRight size={15} />
              </button>
            </div>
            <div className="welcome-footnote"><span className="footnote-line" /> Built for reading, not guessing.</div>
          </section>
        ) : (
          <section className="document-workspace" aria-label="Document question and answer workspace">
            <aside className="document-rail">
              <div className="rail-label">YOUR WORKSPACE</div>
              <div className="document-card">
                <div className="document-icon"><FileText size={18} /></div>
                <div className="document-meta">
                  <span className="document-name" title={document.name}>{document.name}</span>
                  <span className="document-status"><Check size={12} /> Ready to ask</span>
                </div>
                <button className="icon-button remove-button" type="button" onClick={() => void removeDocument()} aria-label="Remove document" title="Remove document">
                  <X size={16} />
                </button>
              </div>
              <div className="document-details">
                <span>{document.page_count ? `${document.page_count} pages` : 'Plain text'}</span>
                <span className="detail-separator" />
                <span>{document.chunk_count} passages indexed</span>
              </div>
              {demoMode && <div className="demo-banner"><Sparkles size={14} /> Demo answers use a simple local matcher.</div>}
              <button className="new-document-button" type="button" onClick={() => void removeDocument()}>
                <Plus size={15} /> New document
              </button>
              <div className="rail-tip">
                <span className="tip-icon"><BookOpenText size={15} /></span>
                <p>Answers are grounded in your document. Each source opens the passage behind it.</p>
              </div>
              <div className="rail-bottom"><ShieldCheck size={14} /> {demoMode ? 'Local memory only' : providerReady ? 'Passages sent to AI provider' : 'AI provider needs setup'}</div>
            </aside>

            <div className="chat-column">
              <div className="chat-heading">
                <div>
                  <div className="eyebrow chat-eyebrow"><MessageSquareText size={14} /> DOCUMENT Q&A</div>
                  <h1>Ask away<span className="brand-period">.</span></h1>
                </div>
                {hasConversation && (
                  <button className="clear-button" type="button" onClick={() => { setMessages([]); setActiveCitation(null); setError('') }}>
                    <RotateCcw size={14} /> Clear chat
                  </button>
                )}
              </div>

              <div className={`conversation ${hasConversation ? 'has-messages' : ''}`} aria-live="polite" aria-busy={busy}>
                {!hasConversation ? (
                  <div className="empty-chat">
                    <div className="empty-chat-mark"><BookOpenText size={24} /></div>
                    <h2>What would you like to know?</h2>
                    <p>Choose a starting point, or ask in your own words.</p>
                    <div className="prompt-list">
                      {starterQuestions.map((prompt, index) => (
                        <button className="prompt-button" type="button" key={prompt} onClick={() => void ask(prompt)}>
                          <span className="prompt-number">0{index + 1}</span>
                          <span>{prompt}</span>
                          <ArrowUpRight size={15} />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="message-list">
                    {messages.map((message) => (
                      <article className={`message message-${message.role}`} key={message.id}>
                        {message.role === 'assistant' && <div className="assistant-avatar"><Sparkles size={15} /></div>}
                        <div className="message-content">
                          <div className="message-label">{message.role === 'assistant' ? 'MARGINALIA' : 'YOU'}</div>
                          <p>{message.text}</p>
                          {message.citations && message.citations.length > 0 && (
                            <div className="citations">
                              <span className="citation-label">SOURCES</span>
                              {message.citations.map((citation) => (
                                <button className="citation-link" type="button" key={citation.id} onClick={() => setActiveCitation(citation)}>
                                  <BookOpenText size={13} />
                                  {citation.page ? `Page ${citation.page}` : `Passage ${citation.id.slice(1)}`}
                                  <ArrowUpRight size={12} />
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                    {busy && <div className="thinking-row"><span className="assistant-avatar"><Sparkles size={15} /></span><span className="thinking-dots"><i /><i /><i /></span><span>Looking through your document</span></div>}
                    <div ref={endOfChat} />
                  </div>
                )}
              </div>

              {activeCitation && (
                <section className="source-panel" aria-label="Citation source passage">
                  <div className="source-panel-top">
                    <div><span className="source-kicker">SOURCE PASSAGE</span><strong>{activeCitation.document}</strong></div>
                    <button className="icon-button" type="button" aria-label="Close source passage" onClick={() => setActiveCitation(null)}><X size={16} /></button>
                  </div>
                  <p>“{activeCitation.passage}”</p>
                  <span className="source-location">{activeCitation.page ? `Page ${activeCitation.page}` : 'Text passage'} · {activeCitation.start > 0 ? `Around character ${activeCitation.start}` : 'Beginning of document'}</span>
                </section>
              )}

              {error && <div className="error-message" role="alert"><CircleHelp size={16} /><span>{error}</span><button type="button" aria-label="Dismiss message" onClick={() => setError('')}><X size={15} /></button></div>}

              <form className="composer" onSubmit={(event) => { event.preventDefault(); void ask() }}>
                <textarea
                  ref={questionInput}
                  aria-label="Ask a question about your document"
                  placeholder="Ask a question about this document…"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value.slice(0, 1000))}
                  onKeyDown={onQuestionKeyDown}
                  maxLength={1000}
                  disabled={busy}
                  rows={1}
                />
                <div className="composer-footer">
                  <span><span className="composer-lock"><ShieldCheck size={13} /></span> Answers use this document only</span>
                  <button className="send-button" type="submit" disabled={!question.trim() || busy} aria-label="Send question">
                    {busy ? <LoaderCircle className="spin" size={17} /> : <Send size={16} />}
                  </button>
                </div>
              </form>
              <div className="chat-footnote">AI can make mistakes. Check the cited passages for context.</div>
            </div>
          </section>
        )}
      </main>
      <footer className="site-footer">
        <span>READ WITH INTENTION</span>
        <span className="footer-mark"><span /> A quieter way to understand more.</span>
        <button type="button" className="footer-about" onClick={() => setError('Marginalia helps you explore your own documents. Answers are based only on retrieved passages.')}>About <ChevronDown size={13} /></button>
      </footer>
    </div>
  )
}

export default App