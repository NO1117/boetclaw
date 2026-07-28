import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ListTodo,
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Pause,
  PlayCircle,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  controlTaskQueue,
  createTaskAdvanced,
  fetchTaskQueueStats,
  fetchTasksPaged,
  openTaskEventsStream,
  type Task,
  type TaskQueueStats,
} from '../services/api'
import './TaskMonitor.css'

const STATUS_ICON: Record<string, typeof Clock> = {
  pending: Clock,
  queued: Clock,
  scheduled: Clock,
  running: Loader2,
  leased: Loader2,
  retry_wait: Clock,
  completed: CheckCircle,
  failed: XCircle,
  cancelled: XCircle,
  dead_letter: XCircle,
  interrupted: XCircle,
}

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'running', label: '运行中' },
  { value: 'pending', label: '排队' },
  { value: 'scheduled', label: '计划' },
  { value: 'retry_wait', label: '重试等待' },
  { value: 'failed', label: '已失败' },
  { value: 'dead_letter', label: '死信' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
  { value: 'interrupted', label: '已中断' },
]

const STATUS_LABEL: Record<string, string> = {
  pending: '排队',
  queued: '排队',
  scheduled: '计划',
  running: '运行中',
  leased: '已领取',
  retry_wait: '重试等待',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  dead_letter: '死信',
  interrupted: '已中断',
  cancelling: '取消中',
}

interface Props {
  onSelectTask: (task: Task) => void
}

export default function TaskMonitor({ onSelectTask }: Props) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [stats, setStats] = useState<TaskQueueStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [priority, setPriority] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')
  const [query, setQuery] = useState('')
  const [sseConnected, setSseConnected] = useState(false)
  const [queueBusy, setQueueBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [page, queueStats] = await Promise.all([
        fetchTasksPaged({
          status: statusFilter || undefined,
          q: query.trim() || undefined,
          limit: 100,
        }),
        fetchTaskQueueStats(),
      ])
      setTasks(page.items)
      setStats(queueStats)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [query, statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const close = openTaskEventsStream({
      onEvent: () => { void load() },
      onConnectionChange: setSseConnected,
      onReset: () => { void load() },
    })
    const fallback = setInterval(() => {
      if (!sseConnected) void load()
    }, sseConnected ? 15000 : 5000)
    return () => {
      close()
      clearInterval(fallback)
    }
  }, [load, sseConnected])

  const handleCreate = async () => {
    if (!title.trim() || !prompt.trim()) return
    const scheduledIso = scheduledAt
      ? new Date(scheduledAt).toISOString()
      : ''
    await createTaskAdvanced({
      title,
      prompt,
      auto_run: !scheduledIso,
      scheduled_at: scheduledIso,
      priority,
    })
    setTitle('')
    setPrompt('')
    setScheduledAt('')
    setPriority(0)
    setShowCreate(false)
    void load()
  }

  const toggleQueue = async () => {
    if (!stats) return
    setQueueBusy(true)
    try {
      const next = await controlTaskQueue(!stats.paused)
      setStats(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setQueueBusy(false)
    }
  }

  const counts = useMemo(() => {
    const base: Record<string, number> = { all: 0 }
    for (const opt of STATUS_OPTIONS) {
      if (opt.value) base[opt.value] = 0
    }
    const source = stats?.status_counts || {}
    base.all = Object.values(source).reduce((sum, n) => sum + n, 0)
    for (const [status, count] of Object.entries(source)) {
      const key = status === 'queued' ? 'pending' : status
      base[key] = (base[key] || 0) + count
    }
    return base
  }, [stats])

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

  const formatLocalTime = (iso: string) => {
    if (!iso) return '—'
    const date = new Date(iso)
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('zh-CN')
  }

  return (
    <div className="task-monitor">
      <div className="panel-header">
        <div className="panel-title">
          <ListTodo size={16} />
          <span>运行中心</span>
          <span className={`sse-indicator ${sseConnected ? 'online' : 'offline'}`} title={sseConnected ? 'SSE 已连接' : 'SSE 降级轮询'}>
            {sseConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          </span>
        </div>
        <div className="panel-actions">
          <button className="icon-btn" onClick={() => void load()} title="刷新" aria-label="刷新任务">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button
            className="action-btn"
            disabled={queueBusy || !stats}
            onClick={() => void toggleQueue()}
            title={stats?.paused ? '恢复队列' : '暂停队列'}
          >
            {stats?.paused ? <PlayCircle size={14} /> : <Pause size={14} />}
            {stats?.paused ? '恢复' : '暂停'}
          </button>
          <button className="action-btn" onClick={() => setShowCreate(!showCreate)}>
            <Play size={14} /> 新建
          </button>
        </div>
      </div>

      {stats && (
        <div className="queue-stats-bar" aria-label="队列统计">
          <span>深度 {stats.queue_depth}</span>
          <span>死信 {stats.dead_letter_count}</span>
          <span>重试 {stats.retry_total}</span>
          <span>{stats.paused ? '已暂停' : '调度中'}</span>
        </div>
      )}

      <div className="task-filters">
        {STATUS_OPTIONS.map(opt => {
          const count = opt.value === '' ? counts.all : counts[opt.value] ?? 0
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
          <label className="create-field">
            计划执行（本地时间，留空则立即运行）
            <input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} />
          </label>
          <label className="create-field">
            优先级
            <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value) || 0)} />
          </label>
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
        {!error && !loading && tasks.length === 0 && (
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
        {tasks.map(task => {
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
                <Icon size={16} className={task.status === 'running' || task.status === 'leased' ? 'spin' : ''} />
              </div>
              <div className="task-info">
                <div className={`task-status-label status-${task.status}`}>
                  {STATUS_LABEL[task.status] || task.status}
                </div>
                <div className="task-title">{task.title}</div>
                <div className="task-meta">
                  <span className={`badge ${task.status}`}>{task.status}</span>
                  {task.agent_id && <span className="badge gateway">{task.agent_id}</span>}
                  {task.scheduled_at && (
                    <span className="time mono">计划 {formatLocalTime(task.scheduled_at)}</span>
                  )}
                  <span className="time mono">{formatDuration(task)}</span>
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
