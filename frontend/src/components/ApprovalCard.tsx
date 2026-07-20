import { useEffect, useState } from 'react'
import { ShieldAlert, Check, X } from 'lucide-react'
import { fetchApprovals, resumeApproval, type ApprovalRequest } from '../services/api'

export default function ApprovalCard() {
  const [pending, setPending] = useState<ApprovalRequest[]>([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState<Set<string>>(new Set())

  const load = async () => {
    try {
      const data = await fetchApprovals()
      setPending(data.pending)
      setError('')
    } catch (e) {
      setError(`审批列表加载失败：${e}`)
    }
  }

  useEffect(() => {
    void load()
    const timer = setInterval(() => void load(), 5000)
    return () => clearInterval(timer)
  }, [])

  const handle = async (req: ApprovalRequest, decision: string) => {
    if (!req.execution_ref || req.status !== 'pending' || submitting.has(req.id)) return
    setSubmitting(current => new Set(current).add(req.id))
    try {
      setError('')
      await resumeApproval(req.id, req.execution_ref, decision)
      await load()
    } catch (e) {
      await load()
      setError(`审批恢复失败：${e}`)
    } finally {
      setSubmitting(current => {
        const next = new Set(current)
        next.delete(req.id)
        return next
      })
    }
  }

  if (pending.length === 0 && !error) return null

  return (
    <>
      {error && <div className="approval-card">{error}</div>}
      {pending.map(req => (
        <div className="approval-card" key={req.id}>
          <h4><ShieldAlert size={14} /> 工具调用需人工审批：{req.tool}</h4>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8 }}>
            <div>状态：{req.status}{req.decision ? `（${req.decision}）` : ''}</div>
            <div>Agent：{req.execution_ref?.agent_id ?? '未知'}</div>
            <div>线程：{(req.execution_ref?.thread_id ?? req.thread_id) || '未知'}</div>
            <div>工具：{req.tool}</div>
            <div>执行引用：{req.execution_ref
              ? `${req.execution_ref.interrupt_type}/${req.execution_ref.interrupt_id}`
              : '不可恢复'}</div>
          </div>
          <div style={{ marginBottom: 8 }}>
            {req.findings.map((f, i) => (
              <div className="finding-row" key={i}>
                <span className={`finding-sev sev-${f.severity}`}>{f.severity}</span>
                {f.message} <span style={{ color: 'var(--text-muted)' }}>（{f.guardian}）</span>
              </div>
            ))}
          </div>
          <details style={{ marginBottom: 8 }}>
            <summary>工具参数与风险快照</summary>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
              {JSON.stringify({ args: req.args, findings: req.findings }, null, 2)}
            </pre>
          </details>
          {!req.execution_ref && (
            <p style={{ color: 'var(--danger)', fontSize: 13 }}>
              此历史审批缺少执行引用，只能查看，不能恢复。
            </p>
          )}
          {req.status === 'resuming' && (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>正在恢复原执行图，请勿重复提交。</p>
          )}
          {req.error && (
            <p style={{ color: 'var(--danger)', fontSize: 13 }}>{req.error}</p>
          )}
          <div className="confirm-actions">
            <button
              className="mgr-btn"
              disabled={!req.execution_ref || req.status !== 'pending' || submitting.has(req.id)}
              onClick={() => void handle(req, 'approve')}
            ><Check size={13} /> 批准</button>
            <button
              className="mgr-btn danger"
              disabled={!req.execution_ref || req.status !== 'pending' || submitting.has(req.id)}
              onClick={() => void handle(req, 'reject')}
            ><X size={13} /> 拒绝</button>
          </div>
        </div>
      ))}
    </>
  )
}
