import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

type Props = { text: string; label?: string; title?: string }

// File names mentioned by the model are shown as plain text on purpose: clickable sources
// come only from the backend's retrieved-source list, never from text position.
const components: Components = {
  ol: ({ children }) => <ol className="steps">{children}</ol>,
  li: ({ children }) => <li><div className="li-body">{children}</div></li>,
  table: ({ children }) => <div className="tablewrap"><table>{children}</table></div>,
  pre: ({ children }) => <pre className="md-pre">{children}</pre>,
  code: ({ className, children }) => {
    const str = String(children ?? '')
    if (/language-/.test(className ?? '') || str.includes('\n'))
      return <code className={className}>{str.replace(/\n$/, '')}</code>
    return <code className="inline">{children}</code>
  },
  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
}

export default function Answer({ text, label = '✦ LOCALREPO ANALYSIS', title }: Props) {
  return (
    <div className="analysis">
      <div className="analysis-label">{label}</div>
      {title && <div className="analysis-title">{title}</div>}
      <div className={'md' + (title ? ' file' : '')}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>
      </div>
    </div>
  )
}
