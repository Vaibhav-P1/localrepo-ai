import { Children, useMemo } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

export type Source = { file: string; start_line: number; end_line: number }

type Props = {
  text: string
  files: string[]
  sources: Source[]
  onOpen: (file: string, hl?: [number, number]) => void
}

const PATH_RE = /([\w@.-]+(?:\/[\w@.-]+)*\.[A-Za-z0-9]{1,5})\b/g

export default function Answer({ text, files, sources, onOpen }: Props) {
  const resolve = useMemo(() => {
    const set = new Set(files)
    const byName = new Map<string, string[]>()
    for (const f of files) {
      const parts = f.split('/')
      for (let i = 0; i < parts.length; i++) {
        const k = parts.slice(i).join('/')
        byName.set(k, [...(byName.get(k) ?? []), f])
      }
    }
    return (tok: string): string | null => {
      const t = tok.replace(/^\.\//, '')
      if (set.has(t)) return t
      const c = byName.get(t)
      return c && c.length === 1 ? c[0] : null
    }
  }, [files])

  const open = (file: string) => {
    const s = sources.find(x => x.file === file)
    onOpen(file, s ? [s.start_line, s.end_line] : undefined)
  }

  const chip = (file: string, label: string, key?: string | number) => (
    <button key={key} className="pathchip" title={file} onClick={() => open(file)}>📄 {label}</button>
  )

  // turn file paths found in plain text into clickable chips
  const linkify = (children: ReactNode): ReactNode =>
    Children.map(children, (child, ci) => {
      if (typeof child !== 'string') return child
      const out: ReactNode[] = []
      let last = 0
      for (const m of child.matchAll(PATH_RE)) {
        const file = resolve(m[1])
        if (!file) continue
        const idx = m.index ?? 0
        if (idx > last) out.push(child.slice(last, idx))
        out.push(chip(file, m[1], `${ci}-${idx}`))
        last = idx + m[1].length
      }
      if (!out.length) return child
      if (last < child.length) out.push(child.slice(last))
      return out
    })

  const components: Components = {
    p: ({ children }) => <p>{linkify(children)}</p>,
    li: ({ children }) => <li><div className="li-body">{linkify(children)}</div></li>,
    td: ({ children }) => <td>{linkify(children)}</td>,
    strong: ({ children }) => <strong>{linkify(children)}</strong>,
    em: ({ children }) => <em>{linkify(children)}</em>,
    ol: ({ children }) => <ol className="steps">{children}</ol>,
    table: ({ children }) => <div className="tablewrap"><table>{children}</table></div>,
    pre: ({ children }) => <pre className="md-pre">{children}</pre>,
    code: ({ className, children }) => {
      const str = String(children ?? '')
      const isBlock = /language-/.test(className ?? '') || str.includes('\n')
      if (isBlock) return <code className={className}>{str.replace(/\n$/, '')}</code>
      const file = resolve(str.trim())
      if (file) return chip(file, str.trim())
      return <code className="inline">{children}</code>
    },
    a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  }

  return (
    <div className="analysis">
      <div className="analysis-label">✦ LOCALREPO ANALYSIS</div>
      <div className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>
      </div>
    </div>
  )
}
