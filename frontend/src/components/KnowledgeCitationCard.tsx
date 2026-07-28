import type { KnowledgeCitationDto } from '../services/api'

interface Props {
  citations: KnowledgeCitationDto[]
  onPreview: (citation: KnowledgeCitationDto) => void
}

function locationLabel(location: Record<string, unknown>) {
  if (location.page) return `第 ${location.page} 页`
  if (location.sheet) return `工作表 ${location.sheet}`
  if (location.slide) return `幻灯片 ${location.slide}`
  if (location.section) return String(location.section)
  return '未知位置'
}

export default function KnowledgeCitationCard({ citations, onPreview }: Props) {
  if (!citations.length) return null
  return (
    <div className="context-card knowledge-citation-card" aria-label="知识库引用">
      <div className="run-context-header">知识库引用</div>
      <ul className="mgr-list">
        {citations.map(c => (
          <li key={`${c.document_id}-${c.chunk_id}`}>
            <button
              type="button"
              className="mgr-item"
              onClick={() => onPreview(c)}
            >
              <div className="mgr-item-main">
                <strong>{c.document_name}</strong>
                <span className="pill">{c.knowledge_base_name}</span>
                <span>{locationLabel(c.location)}</span>
                {c.snippet && <span className="mono">{c.snippet.slice(0, 80)}…</span>}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
