import { useState } from 'react'
import { approveMemory, rejectMemory, updateMemory, type MemoryCandidateDto } from '../services/api'

interface Props {
  agentId: string
  candidate: MemoryCandidateDto
  onResolved: () => void
}

export default function MemoryCandidateBar({ agentId, candidate, onResolved }: Props) {
  const [content, setContent] = useState(candidate.content)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async (action: 'approve' | 'reject' | 'edit') => {
    setBusy(true)
    setError('')
    try {
      if (action === 'reject') {
        await rejectMemory(agentId, candidate.id)
      } else if (action === 'edit') {
        await updateMemory(agentId, candidate.id, { content })
        await approveMemory(agentId, candidate.id)
      } else {
        await approveMemory(agentId, candidate.id)
      }
      onResolved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="memory-candidate-bar" role="region" aria-label="记忆候选确认">
      <div className="memory-candidate-head">
        <strong>检测到可保存的长期记忆</strong>
        <span className="pill">待确认</span>
      </div>
      {!editing ? (
        <p>{candidate.summary}</p>
      ) : (
        <textarea value={content} onChange={e => setContent(e.target.value)} rows={3} aria-label="编辑候选记忆" />
      )}
      {error && <div className="detail-action-error">{error}</div>}
      <div className="memory-item-actions">
        <button type="button" className="mgr-btn primary" disabled={busy} onClick={() => void run('approve')}>保存</button>
        <button type="button" className="mgr-btn secondary" disabled={busy} onClick={() => void run('reject')}>忽略</button>
        {!editing ? (
          <button type="button" className="mgr-btn secondary" disabled={busy} onClick={() => setEditing(true)}>编辑后保存</button>
        ) : (
          <button type="button" className="mgr-btn primary" disabled={busy} onClick={() => void run('edit')}>确认保存</button>
        )}
      </div>
    </div>
  )
}
