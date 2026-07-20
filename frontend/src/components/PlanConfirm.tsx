import { useState } from 'react'
import { ClipboardList, Check, X, Loader2, Pencil } from 'lucide-react'
import { confirmPlan, type ExecutionRef } from '../services/api'

interface Props {
  executionRef: ExecutionRef
  todos: unknown[]
  onResolved: (response: string) => void
}

function todoText(t: unknown): string {
  if (typeof t === 'string') return t
  if (t && typeof t === 'object') {
    const o = t as Record<string, unknown>
    return String(o.content ?? o.title ?? o.task ?? JSON.stringify(o))
  }
  return String(t)
}

export default function PlanConfirm({ executionRef, todos, onResolved }: Props) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(todos.map(todoText).join('\n'))
  const [error, setError] = useState('')

  const handle = async (decision: string) => {
    setBusy(true)
    setError('')
    try {
      const editedTodos = decision === 'edit'
        ? draft.split('\n').map(line => line.trim()).filter(Boolean)
        : undefined
      const result = await confirmPlan(executionRef, decision, editedTodos)
      setDone(true)
      const fallback = decision === 'approve'
        ? '计划已批准，继续执行。'
        : decision === 'edit'
          ? '计划已编辑并提交，继续执行。'
          : '计划已拒绝。'
      onResolved(String(result.response ?? fallback))
    } catch (e) {
      setError(`计划确认失败：${e}`)
    } finally {
      setBusy(false)
    }
  }

  if (done) return null

  return (
    <div className="plan-confirm">
      <h4><ClipboardList size={14} /> 智能体已生成执行计划，请确认</h4>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
        原 Agent：{executionRef.agent_id} · 线程：{executionRef.thread_id} · 中断：{executionRef.interrupt_id}
      </p>
      {todos.length > 0 ? (
        <ul>
          {todos.map((t, i) => <li key={i}>{todoText(t)}</li>)}
        </ul>
      ) : (
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>计划已就绪。</p>
      )}
      {editing && (
        <textarea
          className="plan-edit-textarea"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder="每行一个计划步骤"
          disabled={busy}
        />
      )}
      {error && <p style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</p>}
      <div className="confirm-actions">
        <button className="mgr-btn" disabled={busy} onClick={() => void handle('approve')}>
          {busy ? <Loader2 size={13} className="spin" /> : <Check size={13} />} 批准执行
        </button>
        <button
          className="mgr-btn secondary"
          disabled={busy}
          onClick={() => {
            if (!editing) {
              setEditing(true)
              return
            }
            void handle('edit')
          }}
        >
          <Pencil size={13} /> {editing ? '提交编辑' : '编辑计划'}
        </button>
        <button className="mgr-btn danger" disabled={busy} onClick={() => void handle('reject')}>
          <X size={13} /> 拒绝
        </button>
      </div>
    </div>
  )
}
