import { useEffect, useState } from 'react'
import { Clock, Trash2, Plus, Activity, Play, Save } from 'lucide-react'
import {
  fetchCronJobs,
  createCronJob,
  deleteCronJob,
  fetchCronHistory,
  fetchHeartbeat,
  setCronEnabled,
  triggerCronJob,
  updateCronJob,
  updateHeartbeat,
  type CronJob,
  type CronRunRecord,
  type HeartbeatConfig,
} from '../services/api'

export default function CronManager() {
  const [jobs, setJobs] = useState<CronJob[]>([])
  const [history, setHistory] = useState<CronRunRecord[]>([])
  const [heartbeat, setHeartbeat] = useState<HeartbeatConfig | null>(null)
  const [form, setForm] = useState({ name: '', cron: '', prompt: '', channel: '' })
  const [editing, setEditing] = useState<Record<string, Partial<CronJob>>>({})
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [c, h, hist] = await Promise.all([fetchCronJobs(), fetchHeartbeat(), fetchCronHistory()])
      setJobs(c.jobs)
      setHeartbeat(h)
      setHistory(hist.history)
    } catch { /* ignore */ }
  }

  useEffect(() => { void load() }, [])

  const handleCreate = async () => {
    setError('')
    if (!form.name || !form.cron || !form.prompt) {
      setError('名称、Cron 表达式与提示词均为必填')
      return
    }
    try {
      await createCronJob(form)
      setForm({ name: '', cron: '', prompt: '', channel: '' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (id: string) => {
    await deleteCronJob(id)
    await load()
  }

  const startEdit = (job: CronJob) => {
    setEditing(prev => ({
      ...prev,
      [job.id]: {
        name: job.name,
        cron: job.cron,
        prompt: job.prompt,
        channel: job.channel,
        chat_id: job.chat_id,
        agent_id: job.agent_id,
      },
    }))
  }

  const handleSave = async (id: string) => {
    await updateCronJob(id, editing[id])
    setEditing(prev => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    await load()
  }

  const handleEnable = async (job: CronJob) => {
    await setCronEnabled(job.id, !job.enabled)
    await load()
  }

  const handleTrigger = async (job: CronJob) => {
    setError('')
    try {
      await triggerCronJob(job.id)
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const toggleHeartbeat = async () => {
    if (!heartbeat) return
    const updated = await updateHeartbeat({ enabled: !heartbeat.enabled })
    setHeartbeat(updated)
  }

  return (
    <div>
      <div className="mgr-section-title">新建定时任务</div>
      <div className="mgr-form">
        <input placeholder="任务名称" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        <input placeholder="Cron 表达式，如 0 8 * * *" value={form.cron} onChange={e => setForm({ ...form, cron: e.target.value })} />
        <textarea placeholder="提示词（触发时发送给智能体）" rows={2} value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })} />
        <input placeholder="回发渠道（可选，如 feishu）" value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })} />
        {error && <span style={{ color: 'var(--error)', fontSize: 12 }}>{error}</span>}
        <button className="mgr-btn" onClick={() => void handleCreate()}><Plus size={13} /> 创建任务</button>
      </div>

      <div className="mgr-section-title">已注册任务</div>
      <div className="mgr-list">
        {jobs.length === 0 && <div className="empty-hint">暂无定时任务。</div>}
        {jobs.map(j => (
          <div className="mgr-item" key={j.id}>
            <div className="mgr-item-main">
              <h4><Clock size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{j.name}</h4>
              {editing[j.id] ? (
                <div className="cron-edit-grid">
                  <input value={editing[j.id].name || ''} onChange={e => setEditing(prev => ({ ...prev, [j.id]: { ...prev[j.id], name: e.target.value } }))} />
                  <input value={editing[j.id].cron || ''} onChange={e => setEditing(prev => ({ ...prev, [j.id]: { ...prev[j.id], cron: e.target.value } }))} />
                  <input value={editing[j.id].channel || ''} placeholder="channel" onChange={e => setEditing(prev => ({ ...prev, [j.id]: { ...prev[j.id], channel: e.target.value } }))} />
                  <textarea value={editing[j.id].prompt || ''} rows={2} onChange={e => setEditing(prev => ({ ...prev, [j.id]: { ...prev[j.id], prompt: e.target.value } }))} />
                </div>
              ) : (
                <>
                  <p><code>{j.cron}</code> · {j.prompt.slice(0, 60)}{j.channel ? ` · → ${j.channel}` : ''}</p>
                  <p>run {j.run_count || 0} · last {j.last_run || '—'} · {j.last_status || 'never'}{j.last_error ? ` · ${j.last_error}` : ''}</p>
                </>
              )}
            </div>
            <div className="mgr-actions">
              <span className={`pill ${j.enabled ? 'ok' : 'off'}`}>{j.enabled ? '启用' : '停用'}</span>
              <button className="mgr-btn secondary" onClick={() => void handleEnable(j)}>{j.enabled ? '停用' : '启用'}</button>
              <button className="mgr-btn secondary" disabled={!j.enabled} onClick={() => void handleTrigger(j)}><Play size={12} /> 触发</button>
              {editing[j.id] ? (
                <button className="mgr-btn" onClick={() => void handleSave(j.id)}><Save size={12} /> 保存</button>
              ) : (
                <button className="mgr-btn secondary" onClick={() => startEdit(j)}>编辑</button>
              )}
              <button className="mgr-btn danger" onClick={() => void handleDelete(j.id)}><Trash2 size={12} /></button>
            </div>
          </div>
        ))}
      </div>

      <div className="mgr-section-title">运行历史</div>
      <div className="mgr-list">
        {history.length === 0 && <div className="empty-hint">暂无运行历史。</div>}
        {history.map(r => (
          <div className="mgr-item" key={r.id}>
            <div className="mgr-item-main">
              <h4>{r.job_name} · {r.status}</h4>
              <p>{r.started_at} → {r.finished_at || 'running'}</p>
              <p>trace {r.trace_id || '—'} · run {r.run_id || '—'}{r.error ? ` · ${r.error}` : ''}</p>
            </div>
            <span className={`pill ${r.status === 'success' ? 'ok' : r.status === 'failed' ? 'off' : ''}`}>{r.status}</span>
          </div>
        ))}
      </div>

      {heartbeat && (
        <>
          <div className="mgr-section-title">心跳自检</div>
          <div className="mgr-item">
            <div className="mgr-item-main">
              <h4><Activity size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />每 {heartbeat.interval_minutes} 分钟</h4>
              <p>{heartbeat.prompt}</p>
            </div>
            <div className="mgr-actions">
              <div className={`switch ${heartbeat.enabled ? 'on' : ''}`} role="switch" aria-checked={heartbeat.enabled} onClick={() => void toggleHeartbeat()} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
