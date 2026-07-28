import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { previewKnowledgeSnippet } from '../services/api'

interface Props {
  agentId: string
  kbId: string
  docId: string
  chunkId: string
  title: string
  onClose: () => void
}

export default function KnowledgeSnippetPreview({ agentId, kbId, docId, chunkId, title, onClose }: Props) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      setError('')
      try {
        const res = await previewKnowledgeSnippet(agentId, kbId, docId, chunkId)
        setText(res.text)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    })()
  }, [agentId, kbId, docId, chunkId])

  return (
    <div className="console-modal-overlay" role="dialog" aria-modal="true" aria-label="来源预览">
      <div className="route-card" style={{ maxWidth: 720, width: '90%', margin: '10vh auto', padding: 16 }}>
        <div className="route-card-header">
          <h3>{title}</h3>
          <button type="button" className="mgr-btn compact" onClick={onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        {loading && <p className="page-state loading">加载预览…</p>}
        {error && <p className="detail-action-error">{error}</p>}
        {!loading && !error && (
          <pre className="mono" style={{ whiteSpace: 'pre-wrap', maxHeight: '50vh', overflow: 'auto' }}>{text}</pre>
        )}
      </div>
    </div>
  )
}
