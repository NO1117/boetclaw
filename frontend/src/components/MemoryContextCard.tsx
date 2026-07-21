import { Brain } from 'lucide-react'
import type { MemoryContextSummary } from '../services/api'

interface Props {
  summary: MemoryContextSummary | null
  loading?: boolean
}

export default function MemoryContextCard({ summary, loading }: Props) {
  const mode = summary?.mode ?? 'review'
  const persistent = summary?.persistent ?? false
  const backend = summary?.backend ?? 'sqlite'

  return (
    <div className="context-card memory-context-card">
      <h4 className="run-context-header">
        <Brain size={14} aria-hidden />
        长期记忆
      </h4>
      {loading && <div className="empty-hint">更新记忆上下文…</div>}
      {!loading && !summary && (
        <div className="empty-hint">发送消息后显示本次记忆使用情况。</div>
      )}
      {!loading && summary && (
        <>
          <dl className="context-kv mono">
            <div><dt>模式</dt><dd>{mode}</dd></div>
            <div><dt>后端</dt><dd>{persistent ? backend : `${backend}（非持久）`}</dd></div>
            <div><dt>已保存</dt><dd>{summary.saved_count}</dd></div>
            <div><dt>本次使用</dt><dd>{summary.used_count}</dd></div>
            <div><dt>待审核</dt><dd>{summary.pending_count}</dd></div>
          </dl>
          {summary.items.length > 0 && (
            <ul className="memory-context-items">
              {summary.items.map(item => (
                <li key={item.id}>
                  <span className="pill">{item.scope}</span>
                  <span>{item.summary}</span>
                </li>
              ))}
            </ul>
          )}
          {summary.used_count === 0 && summary.pending_count > 0 && mode === 'review' && (
            <p className="context-footnote">review 模式下待审核记忆不会注入上下文。</p>
          )}
        </>
      )}
    </div>
  )
}
