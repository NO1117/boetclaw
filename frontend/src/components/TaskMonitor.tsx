import { useEffect, useMemo, useState } from 'react'
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
  { value: 'running', label: '运行中' },
  { value: 'pending', label: '待审批' },
  { value: 'failed', label: '已失败' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

interface Props {
  onSelectTask: (task: Task) => void
}

export default function TaskMonitor({ onSelectTask }: Props) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [allTasks, setAllTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [query, setQuery] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [filtered, full] = await Promise.all([
        fetchTasks(statusFilter || undefined),
        fetchTasks(),
      ])
      setTasks(filtered)
      setAllTasks(full)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const interval = setInterval(() => { void load() }, 5000)
    return () => clearInterval(interval)
  }, [statusFilter])

  const handleCreate = async () => {
    if (!title.trim() || !prompt.trim()) return
    await createTask(title, prompt)
    setTitle('')
    setPrompt('')
    setShowCreate(false)
    void load()
  }

  const counts = useMemo(() => {
    const base = { all: allTasks.length, running: 0, pending: 0, failed: 0, completed: 0, cancelled: 0 }
    for (const task of allTasks) {
      if (task.status in base) {
        base[task.status as keyof typeof base] += 1
      }
    }
    return base
  }, [allTasks])

  const visibleTasks = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return tasks
    return tasks.filter(task =>
      [task.id, task.title, task.prompt, task.gateway, task.trace_id]
        .join(' ')
        .toLowerCase()
        .includes(q),
    )
  }, [tasks, query])

  const formatDuration = (task: Task) => {
    const start = Date.parse(task.created_at)
    const end = Date.parse(task.updated_at || task.created_at)
    if (Number.isNaN(start) || Number.isNaN(end)) return '—'
    const sec = Math.max(0, Math.floor((end - start) / 1000))
    const hh = String(Math.floor(sec / 3600)).padStart(2, '0')
    const mm = String(Math.floor((sec % 3600) / 60)).padStart(2, '0')
    const ss = String(sec % 60).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  }

  return (
    <div className="task-monitor">
      <div className="panel-header">
        <div className="panel-title">
          <ListTodo size={16} />
          <span>任务队列</span>
        </div>
        <div className="panel-actions">
          <button className="icon-btn" onClick={() => void load()} title="刷新" aria-label="刷新任务">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button className="action-btn" onClick={() => setShowCreate(!showCreate)}>
            <Play size={14} /> 新建
          </button>
        </div>
      </div>

      <div className="task-filters">
        {STATUS_OPTIONS.map(opt => {
          const count = opt.value === '' ? counts.all : counts[opt.value as keyof typeof counts] ?? 0
          const active = statusFilter === opt.value
          return (
            <button
              key={opt.value || 'all'}
              type="button"
              className={`filter-chip${active ? ' active' : ''}`}
              aria-pressed={active}
              onClick={() => setStatusFilter(opt.value)}
            >
              {opt.label} {count}
            </button>
          )
        })}
        <input
          className="task-search"
          placeholder="搜索任务 ID、Agent 或摘要…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label="搜索任务"
        />
      </div>

      {showCreate && (
        <div className="create-form">
          <input placeholder="任务标题" value={title} onChange={e => setTitle(e.target.value)} />
          <textarea placeholder="任务描述 / Prompt" value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} />
          <button className="action-btn primary" onClick={() => void handleCreate()}>提交任务</button>
        </div>
      )}

      {error && (
        <div className="page-state error compact">
          <div className="page-state-indicator" aria-hidden />
          <p>{error}</p>
          <button type="button" className="action-btn primary" onClick={() => void load()}>重试</button>
        </div>
      )}

      <div className="task-list">
        {!error && loading && tasks.length === 0 && (
          <div className="page-state loading compact">
            <div className="page-state-indicator" aria-hidden />
            <p>正在加载任务…</p>
          </div>
        )}
        {!error && !loading && visibleTasks.length === 0 && (
          <div className="page-state empty compact">
            <div className="page-state-indicator" aria-hidden />
            <p>{query ? '没有匹配搜索条件的任务。' : '暂无任务'}</p>
            {query ? (
              <button type="button" className="action-btn" onClick={() => setQuery('')}>清除搜索</button>
            ) : (
              <button type="button" className="action-btn primary" onClick={() => setShowCreate(true)}>新建任务</button>
            )}
          </div>
        )}
        {visibleTasks.map(task => {
          const Icon = STATUS_ICON[task.status] || Clock
          return (
            <div
              key={task.id}
              className={`task-item status-${task.status}`}
              onClick={() => onSelectTask(task)}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelectTask(task)
                }
              }}
              role="button"
              tabIndex={0}
            >
              <div className="task-status-icon" aria-hidden>
                <Icon size={16} className={task.status === 'running' ? 'spin' : ''} />
              </div>
              <div className="task-info">
                <div className={`task-status-label status-${task.status}`}>
                  {STATUS_LABEL[task.status] || task.status}
                </div>
                <div className="task-title">{task.title}</div>
                <div className="task-meta">
                  <span className={`badge ${task.status}`}>{task.status}</span>
                  {task.gateway && <span className="badge gateway">{task.gateway}</span>}
                  <span className="time mono">{task.gateway || 'default'} · {formatDuration(task)}</span>
                </div>
              </div>
              <div className="task-id mono">#{task.id.slice(0, 8)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
