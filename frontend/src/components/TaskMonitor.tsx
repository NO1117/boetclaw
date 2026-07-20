import { useEffect, useState } from 'react'
import { ListTodo, RefreshCw, Play, CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react'
import { fetchTasks, createTask, type Task } from '../services/api'
import './TaskMonitor.css'

const STATUS_ICON: Record<string, typeof Clock> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
  cancelled: XCircle,
}

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

interface Props {
  onSelectTask: (task: Task) => void
}

export default function TaskMonitor({ onSelectTask }: Props) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setTasks(await fetchTasks(statusFilter || undefined))
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [statusFilter])

  const handleCreate = async () => {
    if (!title.trim() || !prompt.trim()) return
    await createTask(title, prompt)
    setTitle('')
    setPrompt('')
    setShowCreate(false)
    load()
  }

  return (
    <div className="task-monitor">
      <div className="panel-header">
        <div className="panel-title">
          <ListTodo size={16} />
          <span>任务调度</span>
        </div>
        <div className="panel-actions">
          <select
            className="status-filter"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            title="按状态筛选"
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button className="icon-btn" onClick={load} title="刷新">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button className="action-btn" onClick={() => setShowCreate(!showCreate)}>
            <Play size={14} /> 新建
          </button>
        </div>
      </div>

      {showCreate && (
        <div className="create-form">
          <input placeholder="任务标题" value={title} onChange={e => setTitle(e.target.value)} />
          <textarea placeholder="任务描述 / Prompt" value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} />
          <button className="action-btn primary" onClick={handleCreate}>提交任务</button>
        </div>
      )}

      <div className="task-list">
        {tasks.length === 0 && (
          <div className="empty-state">暂无任务</div>
        )}
        {tasks.map(task => {
          const Icon = STATUS_ICON[task.status] || Clock
          return (
            <div key={task.id} className={`task-item status-${task.status}`} onClick={() => onSelectTask(task)}>
              <div className="task-status-icon">
                <Icon size={16} className={task.status === 'running' ? 'spin' : ''} />
              </div>
              <div className="task-info">
                <div className="task-title">{task.title}</div>
                <div className="task-meta">
                  <span className={`badge ${task.status}`}>{task.status}</span>
                  {task.gateway && <span className="badge gateway">{task.gateway}</span>}
                  <span className="time">{new Date(task.created_at).toLocaleString('zh-CN')}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
