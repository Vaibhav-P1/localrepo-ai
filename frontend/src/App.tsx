import { useEffect, useRef, useState } from 'react'
import './index.css'
import Answer from './Answer'

type Status = { connected: boolean; model: string; model_available: boolean }
type Repo = { name: string; file_count: number; languages: string[]; files: string[] }
type Source = { file: string; start_line: number; end_line: number }
type Msg = { q: string; a?: string; sources?: Source[]; error?: string }
type Viewed = { path: string; content: string; hl?: [number, number] }

async function api<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!r.ok) {
    const j = await r.json().catch(() => ({}))
    throw new Error(j.detail || `HTTP ${r.status}`)
  }
  return r.json()
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [path, setPath] = useState('')
  const [repo, setRepo] = useState<Repo | null>(null)
  const [loading, setLoading] = useState(false)
  const [browsing, setBrowsing] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [setupErr, setSetupErr] = useState('')
  const [repoErr, setRepoErr] = useState('')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [viewed, setViewed] = useState<Viewed | null>(null)
  const [explain, setExplain] = useState('')
  const [explaining, setExplaining] = useState(false)
  const [dark, setDark] = useState(() => { try { return localStorage.getItem('lr-dark') === '1' } catch { return false } })
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    try { localStorage.setItem('lr-dark', dark ? '1' : '0') } catch { /* ignore */ }
  }, [dark])
  const endRef = useRef<HTMLDivElement>(null)
  const hlRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const poll = () => api<Status>('/api/status').then(setStatus)
      .catch(() => setStatus({ connected: false, model: 'gemma3:1b', model_available: false }))
    poll()
    const t = setInterval(poll, 5000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])
  useEffect(() => { hlRef.current?.scrollIntoView({ block: 'center' }) }, [viewed])

  async function browse() {
    setBrowsing(true); setRepoErr('')
    try {
      // Desktop app: native Electron dialog. Browser dev mode: backend tkinter picker.
      const picked = window.localrepo
        ? await window.localrepo.pickFolder()
        : (await api<{ path: string | null }>('/api/browse')).path
      if (picked) setPath(picked) // null = user cancelled
    } catch (e) { setRepoErr((e as Error).message) }
    setBrowsing(false)
  }

  const refreshStatus = () => api<Status>('/api/status').then(setStatus).catch(() => undefined)

  async function installModel() {
    setPulling(true); setSetupErr('')
    try { await api('/api/pull-model', {}); await refreshStatus() }
    catch (e) { setSetupErr((e as Error).message) }
    setPulling(false)
  }

  function installOllama() {
    const url = 'https://ollama.com/download/windows'
    if (window.localrepo) window.localrepo.openExternal(url)
    else window.open(url, '_blank', 'noreferrer')
  }

  async function loadRepo() {
    setLoading(true); setRepoErr(''); setMsgs([]); setViewed(null)
    try { setRepo(await api<Repo>('/api/repo', { path })) }
    catch (e) { setRepo(null); setRepoErr((e as Error).message) }
    setLoading(false)
  }

  async function ask(question = q) {
    if (!question.trim() || busy || !repo) return
    setQ(''); setBusy(true)
    setMsgs(m => [...m, { q: question }])
    const upd = (p: Partial<Msg>) => setMsgs(m => m.map((x, i) => i === m.length - 1 ? { ...x, ...p } : x))
    try {
      const r = await api<{ answer: string; sources: Source[] }>('/api/ask', { question })
      upd({ a: r.answer, sources: r.sources })
    } catch (e) { upd({ error: (e as Error).message }) }
    setBusy(false)
  }

  async function open(file: string, hl?: [number, number]) {
    setExplain('')
    try {
      const r = await api<{ path: string; content: string }>(`/api/file?path=${encodeURIComponent(file)}`)
      setViewed({ path: r.path, content: r.content, hl })
    } catch (e) { setViewed({ path: file, content: `// ${(e as Error).message}` }) }
  }

  async function explainFile() {
    if (!viewed) return
    setExplaining(true); setExplain('')
    try { setExplain((await api<{ explanation: string }>('/api/explain', { file: viewed.path })).explanation) }
    catch (e) { setExplain('Error: ' + (e as Error).message) }
    setExplaining(false)
  }

  const treeRows: { label: string; file?: string; depth: number }[] = []
  if (repo) {
    const seen = new Set<string>()
    for (const f of repo.files) {
      const parts = f.split('/')
      for (let i = 0; i < parts.length - 1; i++) {
        const d = parts.slice(0, i + 1).join('/')
        if (!seen.has(d)) { seen.add(d); treeRows.push({ label: '📁 ' + parts[i], depth: i }) }
      }
      treeRows.push({ label: '📄 ' + parts[parts.length - 1], file: f, depth: parts.length - 1 })
    }
  }

  const norm = (p: string) => p.replace(/\\/g, '/').replace(/^\.\//, '').toLowerCase()
  const known = new Set((repo?.files ?? []).map(norm))
  const offline = !!status && !status.connected
  const lines = viewed ? viewed.content.split('\n') : []

  return (
    <div className="app">
      <header>
        <div>
          <span className="brand">LocalRepo <span>AI</span></span>
          <span className="tag">Understand your codebase. Keep your code local.</span>
        </div>
        <div className="status">
          <button className="theme" onClick={() => setDark(d => !d)}>{dark ? '☀ Light' : '☾ Dark'}</button>
          {!status ? '…' : status.connected
            ? <><span className="on badge">● Ollama Connected</span>
              <small>Model: {status.model}{status.model_available ? '' : ` (not pulled — run: ollama pull ${status.model})`} · Local AI</small></>
            : <><span className="off badge">○ Ollama Offline</span>
              <small>Start it with: <code>ollama serve</code></small></>}
        </div>
      </header>
      <div className="main">
        <aside>
          <div className="sec">
            <h4>Repository</h4>
            <div className="row">
              <input className="path" placeholder="C:\path\to\repo" value={path}
                onChange={e => setPath(e.target.value)} onKeyDown={e => e.key === 'Enter' && loadRepo()} />
              <button className="btn alt" disabled={browsing || loading} onClick={browse} title="Pick a folder">{browsing ? '…' : '📁 Browse'}</button>
              <button className="btn" disabled={!path.trim() || loading} onClick={loadRepo}>{loading ? '…' : 'Load'}</button>
            </div>
            {repoErr && <div className="err">{repoErr}</div>}
            {repo && <div style={{ marginTop: 10 }}>
              <div className="repo-name">{repo.name}</div>
              <div>{repo.file_count} files indexed</div>
              <div className="chips">{repo.languages.map(l => <span className="chip" key={l}>{l}</span>)}</div>
              <div className="ok">✓ Repository loaded</div>
              <div className="ok">✓ Local only — nothing leaves this machine</div>
            </div>}
          </div>
          <div className="tree">
            {treeRows.map((r, i) => (
              <div key={i} className={r.file ? (viewed?.path === r.file ? 'sel' : '') : 'dir'}
                style={{ paddingLeft: 10 + r.depth * 12 }} title={r.file}
                onClick={() => r.file && open(r.file)}>{r.label}</div>
            ))}
            {!repo && <div className="dir">No repository loaded</div>}
          </div>
        </aside>
        <section className="chat">
          <div className="panes">
            <div className="ask">
              <div className="msgs">
                {status && !status.connected && <div className="setup">
                  <h3>Set up local AI</h3>
                  <p>LocalRepo AI uses Ollama to run AI locally. Install it, start it, then re-check.</p>
                  <div className="row"><button className="btn" onClick={installOllama}>Install Ollama</button>
                    <button className="btn alt" onClick={refreshStatus}>Re-check</button></div>
                  <p className="hint">Already installed? Start it with <code>ollama serve</code> (or open the Ollama app).</p>
                </div>}
                {status && status.connected && !status.model_available && <div className="setup">
                  <h3>Gemma 3 1B is not installed</h3>
                  <p>Download <code>{status.model}</code> once (about 800 MB). It runs fully on this PC.</p>
                  <div className="row"><button className="btn" disabled={pulling} onClick={installModel}>{pulling ? 'Installing… this can take a few minutes' : 'Install Model'}</button></div>
                  {setupErr && <div className="err">{setupErr}</div>}
                  <p className="hint">Or run <code>ollama pull {status.model}</code> in a terminal.</p>
                </div>}
                {msgs.length === 0 && <div className="empty">
                  {!repo && <div className="hero">
                    <h1>LOCAL<br />REPO <span>AI</span></h1>
                    <p>Understand your codebase. Keep your code local.</p>
                    <div className="hero-note">① Paste a repo path on the left &nbsp; ② Load it &nbsp; ③ Ask anything</div>
                  </div>}
                  {repo && <div className="hero-sm">Ask your codebase anything.</div>}
                  {repo && <div style={{ marginTop: 12 }}>
                    {['Explain the architecture of this project.', 'Where is the entry point?'].map(s =>
                      <span key={s} className="ex" onClick={() => ask(s)}>{s}</span>)}
                  </div>}
                </div>}
                {msgs.map((m, i) => (
                  <div key={i}>
                    <div className="q">{m.q}</div>
                    {m.a === undefined && !m.error && <div className="a">Searching repo &amp; asking local model<span className="dots" /></div>}
                    {m.error && <div className="err">{m.error}</div>}
                    {m.a !== undefined && <>
                      <div className="a"><Answer text={m.a} /></div>
                      <div className="srcs"><h5>RELEVANT SOURCES</h5>
                        {m.sources?.length ? m.sources.map(s => {
                          const ok = known.has(norm(s.file))
                          return ok
                            ? <div key={s.file} className="src" onClick={() => open(s.file, [s.start_line, s.end_line])}>
                              📄 {s.file} <i>· L{s.start_line}–{s.end_line}</i></div>
                            : <div key={s.file} className="src bad">⚠ Source unavailable <i>· {s.file}</i></div>
                        }) : <i style={{ color: 'var(--muted)' }}>No matching files</i>}
                      </div>
                    </>}
                  </div>
                ))}
                <div ref={endRef} />
              </div>
              <div className="inputbar">
                <input disabled={!repo || offline} value={q}
                  placeholder={offline ? 'Ollama is offline — run: ollama serve' : 'Ask a question about this codebase…'}
                  onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && ask()} />
                <button className="btn" disabled={!repo || busy || offline} onClick={() => ask()}>{busy ? 'Thinking…' : 'Ask AI'}</button>
              </div>
            </div>
            {viewed && <div className="viewer">
              <div className="vhead"><span>{viewed.path}</span>
                <button className="btn" disabled={explaining || offline} onClick={explainFile}>{explaining ? 'Explaining…' : 'Explain File'}</button>
              </div>
              <div className="vbody"><pre className="code">
                {lines.map((l, i) => {
                  const n = i + 1
                  const hl = !!viewed.hl && n >= viewed.hl[0] && n <= viewed.hl[1]
                  return <div key={i} ref={hl && n === viewed.hl![0] ? hlRef : undefined}
                    className={'ln' + (hl ? ' hl' : '')}><span className="n">{n}</span><span className="t">{l}</span></div>
                })}
              </pre></div>
              {(explain || explaining) && <div className="explain">
                {explaining
                  ? <span className="dots">Reading file with local model</span>
                  : <Answer label="✦ FILE ANALYSIS" title={viewed.path} text={explain} />}</div>}
            </div>}
          </div>
        </section>
      </div>
    </div>
  )
}
