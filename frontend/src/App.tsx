import { useEffect, useState, type ReactNode } from 'react'
import { Activity, Bot, Database, Drill, FileText, Gauge, ListTodo, LogOut, Settings, ShieldAlert } from 'lucide-react'
import ChatPanel from './components/ChatPanel'
import TaskMonitor from './components/TaskMonitor'
import SidePanel from './components/SidePanel'
import AgentSwitcher from './components/AgentSwitcher'
import ConsoleModal from './components/ConsoleModal'
import ApprovalCard from './components/ApprovalCard'
import SkillsManager from './components/SkillsManager'
import ProviderSettings from './components/ProviderSettings'
import CronManager from './components/CronManager'
import PluginsManager from './components/PluginsManager'
import McpManager from './components/McpManager'
import ChannelsManager from './components/ChannelsManager'
import {
  cancelTask,
  deleteDailyReport,
  deleteDrillingParam,
  deleteLasFile,
  deleteWell,
  deleteWellSection,
  deleteAgent,
  archiveChatSession,
  deleteArtifact,
  deleteChatSession,
  exportChatSession,
  unarchiveChatSession,
  fetchApprovalHistory,
  fetchAgent,
  fetchAgentFiles,
  fetchAgentHistory,
  fetchAgents,
  fetchArtifacts,
  fetchConsoleAuthStatus,
  fetchChatSession,
  fetchChatSessions,
  fetchDailyReports,
  fetchDrillingParams,
  fetchGuardConfig,
  fetchLasFiles,
  fetchTask,
  fetchTraceTimeline,
  fetchWell,
  fetchWells,
  fetchWellSections,
  importLasFile,
  loginConsole,
  logoutConsole,
  uploadLasFile,
  updateDailyReport,
  updateDrillingParam,
  runTask,
  createDailyReport,
  createDrillingParam,
  createWell,
  createWellSection,
  updateLasFile,
  updateWell,
  updateWellSection,
  updateGuardConfig,
  type AgentFileInfo,
  type AgentHistoryItem,
  type AgentInfo,
  type ApprovalRequest,
  type ArtifactInfo,
  type ChatMessage,
  type ChatSessionDetail,
  type ChatSessionSummary,
  type ConsoleAuthStatus,
  type DailyReport,
  type DrillingParam,
  type LasFile,
  type Task,
  type TraceTimeline,
  type Well,
  type WellboreSection,
} from './services/api'
import './App.css'

type SettingsTab = 'skills' | 'providers' | 'scheduler' | 'plugins' | 'mcp' | 'channels' | 'security'

interface AppRoute {
  page: 'chat' | 'tasks' | 'agents' | 'trace' | 'settings' | 'wells' | 'reports' | 'params' | 'las-import' | 'artifacts' | 'not-found'
  taskId?: string
  agentId?: string
  wellId?: string
  filterWellId?: string
  traceId?: string
  settingsTab?: SettingsTab
}

const NAV_ITEMS = [
  { path: '/chat', label: '对话', page: 'chat' },
  { path: '/tasks', label: '任务', page: 'tasks' },
  { path: '/agents', label: 'Agent', page: 'agents' },
  { path: '/trace', label: '追踪', page: 'trace' },
  { path: '/wells', label: '井数据', page: 'wells' },
  { path: '/artifacts', label: '产物', page: 'artifacts' },
  { path: '/settings/skills', label: '设置', page: 'settings' },
]

function stripUiBase(pathname: string) {
  if (pathname === '/ui') return '/'
  if (pathname.startsWith('/ui/')) return pathname.slice(3) || '/'
  return pathname
}

function currentBasePath() {
  return window.location.pathname === '/ui' || window.location.pathname.startsWith('/ui/')
    ? '/ui'
    : ''
}

function parseRoute(pathname = window.location.pathname): AppRoute {
  const [rawPath, query = ''] = pathname.split('?', 2)
  const path = stripUiBase(rawPath).replace(/\/+$/, '') || '/'
  const filterWellId = new URLSearchParams(query || window.location.search).get('well_id') || undefined
  if (path === '/' || path === '/chat') return { page: 'chat' }
  if (path === '/tasks') return { page: 'tasks' }
  if (path.startsWith('/tasks/')) {
    return { page: 'tasks', taskId: decodeURIComponent(path.slice('/tasks/'.length)) }
  }
  if (path === '/agents') return { page: 'agents' }
  if (path.startsWith('/agents/')) {
    return { page: 'agents', agentId: decodeURIComponent(path.slice('/agents/'.length)) }
  }
  if (path === '/trace') return { page: 'trace' }
  if (path.startsWith('/trace/')) {
    return { page: 'trace', traceId: decodeURIComponent(path.slice('/trace/'.length)) }
  }
  if (path === '/wells') return { page: 'wells' }
  if (path.startsWith('/wells/')) {
    return { page: 'wells', wellId: decodeURIComponent(path.slice('/wells/'.length)) }
  }
  if (path === '/reports') return { page: 'reports', filterWellId }
  if (path === '/params') return { page: 'params', filterWellId }
  if (path === '/las/import') return { page: 'las-import', filterWellId }
  if (path === '/artifacts') return { page: 'artifacts', filterWellId }
  if (path === '/settings') return { page: 'settings', settingsTab: 'skills' }
  if (path.startsWith('/settings/')) {
    const raw = path.slice('/settings/'.length)
    const allowed: SettingsTab[] = ['skills', 'providers', 'scheduler', 'plugins', 'mcp', 'channels', 'security']
    return {
      page: 'settings',
      settingsTab: allowed.includes(raw as SettingsTab) ? raw as SettingsTab : 'skills',
    }
  }
  return { page: 'not-found' }
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute())
  const [threadId, setThreadId] = useState<string | null>(null)
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [agentId, setAgentId] = useState<string>('default')
  const [consoleOpen, setConsoleOpen] = useState(false)
  const [restoredMessages, setRestoredMessages] = useState<ChatMessage[]>([])
  const [historyVersion, setHistoryVersion] = useState(0)
  const [authStatus, setAuthStatus] = useState<ConsoleAuthStatus | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    fetchConsoleAuthStatus()
      .then(setAuthStatus)
      .catch(() => setAuthStatus({ login_required: false, authenticated: true }))
      .finally(() => setAuthLoading(false))
  }, [])

  const navigate = (path: string) => {
    const next = `${currentBasePath()}${path}`
    window.history.pushState({}, '', next)
    setRoute(parseRoute(next))
  }

  const handleSelectTask = (task: Task) => {
    if (task.trace_id) setActiveTraceId(task.trace_id)
    if (route.page === 'tasks') {
      navigate(`/tasks/${task.id}`)
      return
    }
    setSelectedTask(task)
  }

  const handleSwitchAgent = (id: string) => {
    setAgentId(id)
    setThreadId(null)
  }

  const effectiveTraceId = route.page === 'trace' && route.traceId ? route.traceId : activeTraceId
  const routePage = route.page
  const settingsTab = route.settingsTab ?? 'skills'

  if (authLoading) {
    return (
      <div className="app auth-shell">
        <div className="login-card">
          <Drill size={28} />
          <h1>BoetClaw</h1>
          <p>正在检查控制台登录状态...</p>
        </div>
      </div>
    )
  }

  if (authStatus?.login_required && !authStatus.authenticated) {
    return (
      <LoginPage
        onLogin={async (password) => {
          const next = await loginConsole(password)
          setAuthStatus(next)
        }}
      />
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="logo">
          <Drill size={24} />
          <div>
            <h1>BoetClaw</h1>
            <span className="subtitle">DeepAgents 钻井智能体系统</span>
          </div>
        </div>
        <nav className="app-nav">
          {NAV_ITEMS.map(item => (
            <button
              key={item.path}
              className={routePage === item.page ? 'active' : ''}
              onClick={() => navigate(item.path)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="header-info">
          {threadId && <span className="thread-badge">Thread: {threadId.slice(0, 8)}</span>}
          {effectiveTraceId && (
            <button className="trace-badge trace-link" onClick={() => navigate(`/trace/${effectiveTraceId}`)}>
              Trace: {effectiveTraceId.slice(0, 8)}
            </button>
          )}
          <AgentSwitcher currentAgent={agentId} onSwitch={handleSwitchAgent} />
          <button className="toolbar-btn" onClick={() => navigate('/settings/skills')}>
            <Settings size={14} /> 设置
          </button>
          {authStatus?.login_required && (
            <button
              className="toolbar-btn"
              onClick={async () => {
                await logoutConsole()
                setAuthStatus({ login_required: true, authenticated: false })
              }}
            >
              <LogOut size={14} /> 退出
            </button>
          )}
        </div>
      </header>

      {routePage === 'chat' && (
        <main className="app-main">
          <section className="main-chat">
            <ChatPanel
              threadId={threadId}
              agentId={agentId}
              onThreadId={setThreadId}
              onTraceUpdate={(traceId) => setActiveTraceId(traceId)}
              initialMessages={restoredMessages}
              historyVersion={historyVersion}
            />
          </section>

          <aside className="main-sidebar">
            <div className="sidebar-top">
              <div className="sidebar-stack">
                <ChatHistoryPanel
                  onRestore={(session) => {
                    setThreadId(session.thread_id)
                    setAgentId(session.agent_id || 'default')
                    setActiveTraceId(session.last_trace_id || null)
                    setRestoredMessages(session.messages)
                    setHistoryVersion(v => v + 1)
                    navigate('/chat')
                  }}
                />
                <TaskMonitor onSelectTask={handleSelectTask} />
              </div>
            </div>
            <div className="sidebar-bottom">
              <ApprovalCard />
              <SidePanel activeTraceId={effectiveTraceId} />
            </div>
          </aside>
        </main>
      )}

      {routePage === 'tasks' && (
        <main className="route-main">
          <PageHeader
            icon={<ListTodo size={18} />}
            title={route.taskId ? `任务 ${route.taskId}` : '任务'}
            description="查看、创建、筛选并管理 Agent 后台任务；可从任务详情重跑、取消或跳转到关联 Trace。"
          />
          <div className="route-grid two-columns">
            <TaskMonitor onSelectTask={handleSelectTask} />
            {route.taskId ? (
              <TaskDetailPanel
                taskId={route.taskId}
                initialTask={selectedTask?.id === route.taskId ? selectedTask : null}
                onTrace={(traceId) => {
                  setActiveTraceId(traceId)
                  navigate(`/trace/${traceId}`)
                }}
                onTaskUpdate={setSelectedTask}
                onClose={() => navigate('/tasks')}
              />
            ) : (
              <SidePanel activeTraceId={effectiveTraceId} />
            )}
          </div>
        </main>
      )}

      {routePage === 'agents' && (
        <main className="route-main">
          <PageHeader
            icon={<Bot size={18} />}
            title={route.agentId ? `Agent ${route.agentId}` : 'Agent 工作区'}
            description="查看工作区详情、切换当前 Agent、删除非默认 Agent，并聚合展示该工作区技能与文件/运行状态。"
          />
          <AgentsPage
            currentAgent={agentId}
            selectedAgentId={route.agentId ?? agentId}
            onSwitch={handleSwitchAgent}
            onSelect={(id) => navigate(`/agents/${id}`)}
            onDeleted={(id) => {
              if (id === agentId) handleSwitchAgent('default')
              navigate('/agents/default')
            }}
          />
        </main>
      )}

      {routePage === 'trace' && (
        <main className="route-main">
          <PageHeader
            icon={<Activity size={18} />}
            title={route.traceId ? `Trace ${route.traceId.slice(0, 8)}` : '追踪'}
            description="查看结构化时间线、事件间隔、分类统计与原始追踪事件。"
          />
          <div className="trace-detail-grid">
            <TraceTimelinePanel traceId={effectiveTraceId} />
            <div className="route-panel tall">
              <SidePanel activeTraceId={effectiveTraceId} />
            </div>
          </div>
        </main>
      )}

      {routePage === 'wells' && (
        <main className="route-main">
          <PageHeader
            icon={<Database size={18} />}
            title={route.wellId ? `井详情 ${route.wellId}` : '井数据'}
            description="管理井、井段、日报、钻井参数与 LAS 文件的领域数据入口。"
          />
          {route.wellId ? (
            <WellDetailPage
              wellId={route.wellId}
              onNavigate={navigate}
              onDeleted={() => navigate('/wells')}
            />
          ) : (
            <WellsPage onOpen={(id) => navigate(`/wells/${id}`)} onNavigate={navigate} />
          )}
        </main>
      )}

      {routePage === 'reports' && (
        <main className="route-main">
          <PageHeader
            icon={<FileText size={18} />}
            title="钻井日报"
            description="按井维护日报、进尺与问题记录，供后续 Agent 生成和审查使用。"
          />
          <ReportsPage initialWellId={route.filterWellId ?? ''} />
        </main>
      )}

      {routePage === 'params' && (
        <main className="route-main">
          <PageHeader
            icon={<Gauge size={18} />}
            title="钻井参数"
            description="维护按井和井深沉淀的 WOB、RPM、ROP、扭矩、泵压等参数。"
          />
          <ParamsPage initialWellId={route.filterWellId ?? ''} />
        </main>
      )}

      {routePage === 'las-import' && (
        <main className="route-main">
          <PageHeader
            icon={<FileText size={18} />}
            title="LAS 导入登记"
            description="登记 LAS 文件路径、曲线与深度范围；实际解析与质量检查将在后续任务接入。"
          />
          <LasImportPage initialWellId={route.filterWellId ?? ''} />
        </main>
      )}

      {routePage === 'artifacts' && (
        <main className="route-main">
          <PageHeader
            icon={<FileText size={18} />}
            title="产物中心"
            description="集中查看 Agent 生成的图表和代码，支持预览、下载，并显示任务、Trace、井号关联元数据。"
          />
          <ArtifactsPage initialWellId={route.filterWellId ?? ''} />
        </main>
      )}

      {routePage === 'settings' && (
        <main className="route-main">
          <PageHeader
            icon={<Settings size={18} />}
            title="设置"
            description="按路由进入技能、模型、调度、插件与安全入口。配置写入和审计历史将在后续子任务补齐。"
          />
          <SettingsPage
            tab={settingsTab}
            agentId={agentId}
            onTabChange={(tab) => navigate(`/settings/${tab}`)}
          />
        </main>
      )}

      {routePage === 'not-found' && (
        <main className="route-main">
          <PageHeader
            icon={<Drill size={18} />}
            title="页面不存在"
            description="请选择顶部导航中的现有页面。"
          />
        </main>
      )}

      {consoleOpen && <ConsoleModal agentId={agentId} onClose={() => setConsoleOpen(false)} />}

      {selectedTask && (
        <div className="task-detail-overlay" onClick={() => setSelectedTask(null)}>
          <div className="task-detail" onClick={e => e.stopPropagation()}>
            <TaskDetailContent
              task={selectedTask}
              onTaskUpdate={setSelectedTask}
              onTrace={(traceId) => {
                setActiveTraceId(traceId)
                setSelectedTask(null)
                navigate(`/trace/${traceId}`)
              }}
              onClose={() => setSelectedTask(null)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function PageHeader({
  icon,
  title,
  description,
}: {
  icon: ReactNode
  title: string
  description: string
}) {
  return (
    <div className="route-header">
      <div className="route-title">
        {icon}
        <h2>{title}</h2>
      </div>
      <p>{description}</p>
    </div>
  )
}

function LoginPage({ onLogin }: { onLogin: (password: string) => Promise<void> }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!password) {
      setError('请输入控制台密码')
      return
    }
    setLoading(true)
    setError('')
    try {
      await onLogin(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app auth-shell">
      <div className="login-card">
        <div className="login-logo">
          <Drill size={28} />
          <div>
            <h1>BoetClaw</h1>
            <span>管理控制台登录</span>
          </div>
        </div>
        <p>请输入 `CONSOLE_PASSWORD` 配置的控制台密码。</p>
        <input
          type="password"
          placeholder="控制台密码"
          value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') void submit()
          }}
          autoFocus
        />
        {error && <div className="login-error">{error}</div>}
        <button className="primary-btn" onClick={() => void submit()} disabled={loading}>
          {loading ? '登录中...' : '登录'}
        </button>
      </div>
    </div>
  )
}

function WellsPage({ onOpen, onNavigate }: { onOpen: (id: string) => void; onNavigate: (path: string) => void }) {
  const [wells, setWells] = useState<Well[]>([])
  const [form, setForm] = useState({ name: '', field: '', operator: '', location: '', status: 'planned' })
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      setWells(await fetchWells())
    } catch (e) {
      setError(String(e))
    }
  }
  useEffect(() => { void load() }, [])

  const handleCreate = async () => {
    if (!form.name.trim()) {
      setError('井名必填')
      return
    }
    setError('')
    try {
      await createWell(form)
      setForm({ name: '', field: '', operator: '', location: '', status: 'planned' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="domain-grid">
      <div className="route-card task-detail-card">
        <h3>新建井</h3>
        <div className="mgr-form">
          <input placeholder="井名，如 XX-1" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <input placeholder="区块/油田" value={form.field} onChange={e => setForm({ ...form, field: e.target.value })} />
          <input placeholder="作业方" value={form.operator} onChange={e => setForm({ ...form, operator: e.target.value })} />
          <input placeholder="位置" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} />
          <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
            <option value="planned">planned</option>
            <option value="drilling">drilling</option>
            <option value="completed">completed</option>
          </select>
          {error && <div className="detail-action-error">{error}</div>}
          <button className="mgr-btn" onClick={() => void handleCreate()}>创建井</button>
        </div>
      </div>
      <div className="route-card">
        <div className="route-card-header">
          <span>井列表</span>
          <div className="mgr-actions">
            <button className="mgr-btn secondary" onClick={() => onNavigate('/reports')}>日报</button>
            <button className="mgr-btn secondary" onClick={() => onNavigate('/params')}>参数</button>
            <button className="mgr-btn secondary" onClick={() => onNavigate('/las/import')}>LAS</button>
            <button className="mgr-btn secondary" onClick={() => void load()}>刷新</button>
          </div>
        </div>
        <div className="route-list">
          {wells.length === 0 && <div className="empty-hint">暂无井数据。</div>}
          {wells.map(well => (
            <button key={well.id} className="route-list-item" onClick={() => onOpen(well.id)}>
              <div>
                <strong>{well.name}</strong>
                <p>{well.field || '—'} · {well.operator || '—'} · {well.location || '—'}</p>
              </div>
              <span className="pill ok">{well.status}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function WellDetailPage({
  wellId,
  onNavigate,
  onDeleted,
}: {
  wellId: string
  onNavigate: (path: string) => void
  onDeleted: () => void
}) {
  const [well, setWell] = useState<Well | null>(null)
  const [sections, setSections] = useState<WellboreSection[]>([])
  const [reports, setReports] = useState<DailyReport[]>([])
  const [params, setParams] = useState<DrillingParam[]>([])
  const [lasFiles, setLasFiles] = useState<LasFile[]>([])
  const [sectionForm, setSectionForm] = useState({ name: '', top_depth: '0', bottom_depth: '0', hole_size: '' })
  const [editingSectionId, setEditingSectionId] = useState('')
  const [wellForm, setWellForm] = useState({ name: '', field: '', operator: '', location: '', status: 'planned' })
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const [w, s, r, p, l] = await Promise.all([
        fetchWell(wellId),
        fetchWellSections(wellId),
        fetchDailyReports(wellId),
        fetchDrillingParams(wellId),
        fetchLasFiles(wellId),
      ])
      setWell(w)
      setWellForm({ name: w.name, field: w.field, operator: w.operator, location: w.location, status: w.status })
      setSections(s)
      setReports(r)
      setParams(p)
      setLasFiles(l)
    } catch (e) {
      setError(String(e))
    }
  }

  useEffect(() => { void load() }, [wellId])

  const handleAddSection = async () => {
    if (!sectionForm.name.trim()) return
    setError('')
    try {
      const payload = {
        well_id: wellId,
        name: sectionForm.name,
        top_depth: Number(sectionForm.top_depth),
        bottom_depth: Number(sectionForm.bottom_depth),
        hole_size: sectionForm.hole_size,
      }
      if (editingSectionId) await updateWellSection(editingSectionId, payload)
      else await createWellSection(payload)
      setEditingSectionId('')
      setSectionForm({ name: '', top_depth: '0', bottom_depth: '0', hole_size: '' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleSaveWell = async () => {
    if (!well || !wellForm.name.trim()) return
    setError('')
    try {
      setWell(await updateWell(well.id, { ...wellForm, metadata: well.metadata }))
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDeleteWell = async () => {
    if (!well || !window.confirm(`确认删除井 ${well.name}？存在关联数据时服务端会拒绝删除。`)) return
    setError('')
    try {
      await deleteWell(well.id)
      onDeleted()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDeleteSection = async (section: WellboreSection) => {
    if (!window.confirm(`确认删除井段 ${section.name}？`)) return
    try {
      await deleteWellSection(section.id)
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="route-card task-detail-card">
      {!well && <div className="empty-hint">加载井详情...</div>}
      {error && <div className="detail-action-error">{error}</div>}
      {well && (
        <>
          <h3>{well.name}</h3>
          <div className="detail-meta">
            <span className="pill ok">{well.status}</span>
            <span>{well.field || '未设置区块'}</span>
            <span>{well.operator || '未设置作业方'}</span>
          </div>
          <div className="mgr-section-title">编辑井</div>
          <div className="mgr-form domain-inline-form">
            <input placeholder="井名" value={wellForm.name} onChange={e => setWellForm({ ...wellForm, name: e.target.value })} />
            <input placeholder="区块/油田" value={wellForm.field} onChange={e => setWellForm({ ...wellForm, field: e.target.value })} />
            <input placeholder="作业方" value={wellForm.operator} onChange={e => setWellForm({ ...wellForm, operator: e.target.value })} />
            <input placeholder="位置" value={wellForm.location} onChange={e => setWellForm({ ...wellForm, location: e.target.value })} />
            <select value={wellForm.status} onChange={e => setWellForm({ ...wellForm, status: e.target.value })}>
              <option value="planned">planned</option>
              <option value="drilling">drilling</option>
              <option value="completed">completed</option>
            </select>
            <button className="mgr-btn" onClick={() => void handleSaveWell()}>保存井信息</button>
            <button className="mgr-btn danger" onClick={() => void handleDeleteWell()}>删除井</button>
          </div>
          <div className="stats-grid domain-stats-grid">
            <div className="stat-card"><div className="stat-value">{sections.length}</div><div className="stat-label">井段</div></div>
            <div className="stat-card"><div className="stat-value">{reports.length}</div><div className="stat-label">日报</div></div>
            <div className="stat-card"><div className="stat-value">{params.length}</div><div className="stat-label">参数</div></div>
            <div className="stat-card"><div className="stat-value">{lasFiles.length}</div><div className="stat-label">LAS</div></div>
          </div>
          <div className="detail-actions domain-nav-actions">
            <button className="action-btn" onClick={() => onNavigate(`/reports?well_id=${encodeURIComponent(wellId)}`)}>查看日报</button>
            <button className="action-btn" onClick={() => onNavigate(`/params?well_id=${encodeURIComponent(wellId)}`)}>查看参数</button>
            <button className="action-btn" onClick={() => onNavigate(`/las/import?well_id=${encodeURIComponent(wellId)}`)}>查看 LAS</button>
            <button className="action-btn" onClick={() => onNavigate(`/artifacts?well_id=${encodeURIComponent(wellId)}`)}>查看产物</button>
          </div>

          <div className="mgr-section-title">{editingSectionId ? '编辑井段' : '新增井段'}</div>
          <div className="mgr-form domain-inline-form">
            <input placeholder="井段名称" value={sectionForm.name} onChange={e => setSectionForm({ ...sectionForm, name: e.target.value })} />
            <input placeholder="顶深" value={sectionForm.top_depth} onChange={e => setSectionForm({ ...sectionForm, top_depth: e.target.value })} />
            <input placeholder="底深" value={sectionForm.bottom_depth} onChange={e => setSectionForm({ ...sectionForm, bottom_depth: e.target.value })} />
            <input placeholder="井眼尺寸" value={sectionForm.hole_size} onChange={e => setSectionForm({ ...sectionForm, hole_size: e.target.value })} />
            <button className="mgr-btn" onClick={() => void handleAddSection()}>{editingSectionId ? '保存井段' : '添加井段'}</button>
            {editingSectionId && <button className="mgr-btn secondary" onClick={() => { setEditingSectionId(''); setSectionForm({ name: '', top_depth: '0', bottom_depth: '0', hole_size: '' }) }}>取消编辑</button>}
          </div>

          <div className="mgr-section-title">井段</div>
          <div className="mgr-list">
            {sections.length === 0 && <div className="empty-hint">暂无井段。</div>}
            {sections.map(section => (
              <div className="mgr-item" key={section.id}>
                <div className="mgr-item-main"><p>{section.name}: {section.top_depth}-{section.bottom_depth}m {section.hole_size}</p></div>
                <div className="mgr-actions">
                  <button className="mgr-btn secondary" onClick={() => { setEditingSectionId(section.id); setSectionForm({ name: section.name, top_depth: String(section.top_depth), bottom_depth: String(section.bottom_depth), hole_size: section.hole_size }) }}>编辑</button>
                  <button className="mgr-btn danger" onClick={() => void handleDeleteSection(section)}>删除</button>
                </div>
              </div>
            ))}
          </div>
          <DomainMiniList title="最近日报" rows={reports.slice(0, 5).map(r => `${r.report_date}: ${r.depth_start}-${r.depth_end}m ${r.summary}`)} />
          <DomainMiniList title="最近参数" rows={params.slice(0, 5).map(p => `${p.measured_depth}m · WOB ${p.wob ?? '—'} · RPM ${p.rpm ?? '—'} · ROP ${p.rop ?? '—'}`)} />
          <DomainMiniList title="LAS 文件" rows={lasFiles.map(l => `${l.filename}: ${l.curves.join(', ') || '未登记曲线'}`)} />
        </>
      )}
    </div>
  )
}

function ReportsPage({ initialWellId }: { initialWellId: string }) {
  const [wells, setWells] = useState<Well[]>([])
  const [reports, setReports] = useState<DailyReport[]>([])
  const [filterWellId, setFilterWellId] = useState(initialWellId)
  const [editingId, setEditingId] = useState('')
  const [error, setError] = useState('')
  const [form, setForm] = useState({ well_id: initialWellId, report_date: '', depth_start: '0', depth_end: '0', summary: '', issues: '' })
  const load = async (wellId = filterWellId) => {
    setError('')
    try {
      const [w, r] = await Promise.all([fetchWells(), fetchDailyReports(wellId)])
      setWells(w)
      setReports(r)
      if (!form.well_id && w[0]) setForm(prev => ({ ...prev, well_id: wellId || w[0].id }))
    } catch (e) {
      setError(String(e))
    }
  }
  useEffect(() => { void load(initialWellId) }, [initialWellId])
  const save = async () => {
    if (!form.well_id || !form.report_date) return
    setError('')
    try {
      const payload = { ...form, depth_start: Number(form.depth_start), depth_end: Number(form.depth_end) }
      if (editingId) await updateDailyReport(editingId, payload)
      else await createDailyReport(payload)
      setEditingId('')
      setForm({ ...form, report_date: '', depth_start: '0', depth_end: '0', summary: '', issues: '' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  const edit = (report: DailyReport) => {
    setEditingId(report.id)
    setForm({ well_id: report.well_id, report_date: report.report_date, depth_start: String(report.depth_start), depth_end: String(report.depth_end), summary: report.summary, issues: report.issues })
  }
  const remove = async (report: DailyReport) => {
    if (!window.confirm(`确认删除 ${report.report_date} 的日报？`)) return
    try {
      await deleteDailyReport(report.id)
      if (editingId === report.id) setEditingId('')
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  return <div className="domain-grid">
    <div className="route-card task-detail-card">
      <h3>{editingId ? '编辑日报' : '新增日报'}</h3>
      {wells.length === 0 && <div className="empty-hint">请先在井数据页创建井。</div>}
      {error && <div className="detail-action-error">{error}</div>}
      <div className="mgr-form">
        <select value={form.well_id} onChange={e => setForm({ ...form, well_id: e.target.value })}>{wells.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
        <input type="date" value={form.report_date} onChange={e => setForm({ ...form, report_date: e.target.value })} />
        <input placeholder="起始井深" value={form.depth_start} onChange={e => setForm({ ...form, depth_start: e.target.value })} />
        <input placeholder="结束井深" value={form.depth_end} onChange={e => setForm({ ...form, depth_end: e.target.value })} />
        <textarea placeholder="日报摘要" rows={2} value={form.summary} onChange={e => setForm({ ...form, summary: e.target.value })} />
        <textarea placeholder="问题记录" rows={2} value={form.issues} onChange={e => setForm({ ...form, issues: e.target.value })} />
        <button className="mgr-btn" onClick={() => void save()}>{editingId ? '保存修改' : '保存日报'}</button>
        {editingId && <button className="mgr-btn secondary" onClick={() => setEditingId('')}>取消编辑</button>}
      </div>
    </div>
    <DomainEntityList
      title="日报记录"
      wells={wells}
      filterWellId={filterWellId}
      onFilter={(value) => { setFilterWellId(value); setForm(prev => ({ ...prev, well_id: value || prev.well_id })); void load(value) }}
      rows={reports.map(report => ({ id: report.id, label: `${report.report_date} · ${report.depth_start}-${report.depth_end}m`, detail: `${report.summary || '无摘要'}${report.issues ? ` · 问题：${report.issues}` : ''}`, onEdit: () => edit(report), onDelete: () => void remove(report) }))}
    />
  </div>
}

function ParamsPage({ initialWellId }: { initialWellId: string }) {
  const [wells, setWells] = useState<Well[]>([])
  const [params, setParams] = useState<DrillingParam[]>([])
  const [filterWellId, setFilterWellId] = useState(initialWellId)
  const [editingId, setEditingId] = useState('')
  const [error, setError] = useState('')
  const [form, setForm] = useState({ well_id: initialWellId, measured_depth: '', wob: '', rpm: '', rop: '', torque: '', pump_pressure: '', flow_rate: '' })
  const load = async (wellId = filterWellId) => {
    setError('')
    try {
      const [w, p] = await Promise.all([fetchWells(), fetchDrillingParams(wellId)])
      setWells(w)
      setParams(p)
      if (!form.well_id && w[0]) setForm(prev => ({ ...prev, well_id: wellId || w[0].id }))
    } catch (e) {
      setError(String(e))
    }
  }
  useEffect(() => { void load(initialWellId) }, [initialWellId])
  const num = (value: string) => value === '' ? null : Number(value)
  const save = async () => {
    if (!form.well_id || !form.measured_depth) return
    setError('')
    try {
      const payload = {
        well_id: form.well_id,
        measured_depth: Number(form.measured_depth),
        wob: num(form.wob),
        rpm: num(form.rpm),
        rop: num(form.rop),
        torque: num(form.torque),
        pump_pressure: num(form.pump_pressure),
        flow_rate: num(form.flow_rate),
      }
      if (editingId) await updateDrillingParam(editingId, payload)
      else await createDrillingParam(payload)
      setEditingId('')
      setForm({ ...form, measured_depth: '', wob: '', rpm: '', rop: '', torque: '', pump_pressure: '', flow_rate: '' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  const edit = (item: DrillingParam) => {
    setEditingId(item.id)
    setForm({ well_id: item.well_id, measured_depth: String(item.measured_depth), wob: String(item.wob ?? ''), rpm: String(item.rpm ?? ''), rop: String(item.rop ?? ''), torque: String(item.torque ?? ''), pump_pressure: String(item.pump_pressure ?? ''), flow_rate: String(item.flow_rate ?? '') })
  }
  const remove = async (item: DrillingParam) => {
    if (!window.confirm(`确认删除 ${item.measured_depth}m 参数记录？`)) return
    try {
      await deleteDrillingParam(item.id)
      if (editingId === item.id) setEditingId('')
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  return <div className="domain-grid">
    <div className="route-card task-detail-card">
      <h3>{editingId ? '编辑参数' : '新增参数'}</h3>
      {error && <div className="detail-action-error">{error}</div>}
      <div className="mgr-form">
        <select value={form.well_id} onChange={e => setForm({ ...form, well_id: e.target.value })}>{wells.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
        <input placeholder="井深" value={form.measured_depth} onChange={e => setForm({ ...form, measured_depth: e.target.value })} />
        <input placeholder="WOB" value={form.wob} onChange={e => setForm({ ...form, wob: e.target.value })} />
        <input placeholder="RPM" value={form.rpm} onChange={e => setForm({ ...form, rpm: e.target.value })} />
        <input placeholder="ROP" value={form.rop} onChange={e => setForm({ ...form, rop: e.target.value })} />
        <input placeholder="Torque" value={form.torque} onChange={e => setForm({ ...form, torque: e.target.value })} />
        <input placeholder="Pump Pressure" value={form.pump_pressure} onChange={e => setForm({ ...form, pump_pressure: e.target.value })} />
        <input placeholder="Flow Rate" value={form.flow_rate} onChange={e => setForm({ ...form, flow_rate: e.target.value })} />
        <button className="mgr-btn" onClick={() => void save()}>{editingId ? '保存修改' : '保存参数'}</button>
        {editingId && <button className="mgr-btn secondary" onClick={() => setEditingId('')}>取消编辑</button>}
      </div>
    </div>
    <DomainEntityList
      title="参数记录"
      wells={wells}
      filterWellId={filterWellId}
      onFilter={(value) => { setFilterWellId(value); setForm(prev => ({ ...prev, well_id: value || prev.well_id })); void load(value) }}
      rows={params.map(item => ({ id: item.id, label: `${item.measured_depth}m · WOB ${item.wob ?? '—'} · RPM ${item.rpm ?? '—'}`, detail: `ROP ${item.rop ?? '—'} · Torque ${item.torque ?? '—'} · Pump ${item.pump_pressure ?? '—'} · Flow ${item.flow_rate ?? '—'}`, onEdit: () => edit(item), onDelete: () => void remove(item) }))}
    />
  </div>
}

function LasImportPage({ initialWellId }: { initialWellId: string }) {
  const [wells, setWells] = useState<Well[]>([])
  const [lasFiles, setLasFiles] = useState<LasFile[]>([])
  const [filterWellId, setFilterWellId] = useState(initialWellId)
  const [editing, setEditing] = useState<LasFile | null>(null)
  const [form, setForm] = useState({ well_id: initialWellId, filename: '', path: '', curves: '', depth_min: '', depth_max: '', status: 'registered' })
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const load = async (wellId = filterWellId) => {
    setError('')
    try {
      const [w, l] = await Promise.all([fetchWells(), fetchLasFiles(wellId)])
      setWells(w)
      setLasFiles(l)
      if (!form.well_id && w[0]) setForm(prev => ({ ...prev, well_id: wellId || w[0].id }))
    } catch (e) {
      setError(String(e))
    }
  }
  useEffect(() => { void load(initialWellId) }, [initialWellId])
  const create = async () => {
    if (!form.well_id || !form.path) return
    setError('')
    try {
      await importLasFile({ well_id: form.well_id, path: form.path, filename: form.filename || undefined })
    } catch (e) {
      setError(String(e))
      return
    }
    setForm({ ...form, filename: '', path: '', curves: '', depth_min: '', depth_max: '', status: 'registered' })
    await load()
  }
  const upload = async () => {
    if (!form.well_id || !selectedFile) return
    setError('')
    try {
      await uploadLasFile({ well_id: form.well_id, file: selectedFile, filename: form.filename || undefined })
    } catch (e) {
      setError(String(e))
      return
    }
    setSelectedFile(null)
    setForm({ ...form, filename: '', path: '', curves: '', depth_min: '', depth_max: '', status: 'registered' })
    await load()
  }
  const startEdit = (item: LasFile) => {
    setEditing(item)
    setForm({ well_id: item.well_id, filename: item.filename, path: item.path, curves: item.curves.join(', '), depth_min: String(item.depth_min ?? ''), depth_max: String(item.depth_max ?? ''), status: item.status })
  }
  const saveEdit = async () => {
    if (!editing) return
    setError('')
    try {
      await updateLasFile(editing.id, {
        ...editing,
        well_id: form.well_id,
        filename: form.filename,
        path: form.path,
        status: form.status,
        curves: form.curves.split(',').map(value => value.trim()).filter(Boolean),
        depth_min: form.depth_min === '' ? null : Number(form.depth_min),
        depth_max: form.depth_max === '' ? null : Number(form.depth_max),
      })
      setEditing(null)
      setForm({ ...form, filename: '', path: '', curves: '', depth_min: '', depth_max: '', status: 'registered' })
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  const remove = async (item: LasFile) => {
    if (!window.confirm(`确认删除 LAS 记录 ${item.filename}？仅会清理系统托管的上传文件和曲线缓存，外部源文件会保留。`)) return
    try {
      await deleteLasFile(item.id)
      if (editing?.id === item.id) setEditing(null)
      await load()
    } catch (e) {
      setError(String(e))
    }
  }
  return <div className="domain-grid">
    <div className="route-card task-detail-card">
      <h3>{editing ? '编辑 LAS 记录' : '导入 LAS'}</h3>
      {error && <div className="detail-action-error">{error}</div>}
      <div className="mgr-form">
        <select value={form.well_id} onChange={e => setForm({ ...form, well_id: e.target.value })}>{wells.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
        <input placeholder="LAS 文件名（可选）" value={form.filename} onChange={e => setForm({ ...form, filename: e.target.value })} />
        {editing ? <>
          <input placeholder="源路径" value={form.path} onChange={e => setForm({ ...form, path: e.target.value })} />
          <input placeholder="曲线，逗号分隔" value={form.curves} onChange={e => setForm({ ...form, curves: e.target.value })} />
          <input placeholder="最小深度" value={form.depth_min} onChange={e => setForm({ ...form, depth_min: e.target.value })} />
          <input placeholder="最大深度" value={form.depth_max} onChange={e => setForm({ ...form, depth_max: e.target.value })} />
          <input placeholder="状态" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} />
          <button className="mgr-btn" onClick={() => void saveEdit()}>保存修改</button>
          <button className="mgr-btn secondary" onClick={() => setEditing(null)}>取消编辑</button>
        </> : <>
          <input type="file" accept=".las,.LAS,.txt" onChange={e => setSelectedFile(e.target.files?.[0] || null)} />
          <input placeholder="或填写服务器 LAS 文件路径" value={form.path} onChange={e => setForm({ ...form, path: e.target.value })} />
          <button className="mgr-btn" disabled={!selectedFile} onClick={() => void upload()}>上传并质检</button>
          <button className="mgr-btn secondary" disabled={!form.path} onClick={() => void create()}>按路径导入</button>
        </>}
      </div>
    </div>
    <DomainEntityList
      title="LAS 记录"
      wells={wells}
      filterWellId={filterWellId}
      onFilter={(value) => { setFilterWellId(value); setForm(prev => ({ ...prev, well_id: value || prev.well_id })); void load(value) }}
      rows={lasFiles.map(item => {
        const quality = item.quality || {}
        return { id: item.id, label: `${item.filename} · ${item.status} · ${item.curves.join(', ') || '—'}`, detail: `${item.depth_min ?? '—'}-${item.depth_max ?? '—'}m · points ${quality.point_count ?? '—'} · nulls ${quality.null_count ?? '—'}`, onEdit: () => startEdit(item), onDelete: () => void remove(item) }
      })}
    />
  </div>
}

function TraceTimelinePanel({ traceId }: { traceId: string | null }) {
  const [timeline, setTimeline] = useState<TraceTimeline | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    if (!traceId) {
      setTimeline(null)
      setError('')
      return
    }
    setLoading(true)
    setError('')
    try {
      setTimeline(await fetchTraceTimeline(traceId))
    } catch (e) {
      setTimeline(null)
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [traceId])

  if (!traceId) {
    return <div className="route-card"><div className="empty-hint">暂无 Trace。请从对话、任务或产物打开关联 Trace。</div></div>
  }

  return (
    <div className="route-card trace-timeline-card">
      <div className="route-card-header">
        <span>结构化时间线</span>
        <button className="mgr-btn secondary" onClick={() => void load()}>刷新</button>
      </div>
      {loading && <div className="empty-hint">加载时间线...</div>}
      {error && <div className="detail-action-error">{error}</div>}
      {!loading && timeline && (
        <>
          <div className="agent-summary-grid">
            <div className="stat-card">
              <div className="stat-value">{timeline.event_count}</div>
              <div className="stat-label">事件数</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{(timeline.duration_ms / 1000).toFixed(2)}s</div>
              <div className="stat-label">总耗时</div>
            </div>
          </div>
          <div className="trace-category-row">
            {Object.entries(timeline.categories).map(([name, count]) => (
              <span className="pill" key={name}>{name}: {count}</span>
            ))}
          </div>
          <div className="trace-timeline-list">
            {timeline.events.map(event => (
              <div className="trace-timeline-item" key={event.id}>
                <div className="trace-timeline-marker">{event.sequence}</div>
                <div className="trace-timeline-body">
                  <div className="trace-timeline-title">
                    <strong>{event.summary}</strong>
                    <span className="pill">{event.category}</span>
                  </div>
                  <p>{event.event_type} · +{event.offset_ms}ms · Δ {event.delta_ms}ms · run {event.run_id || '—'}</p>
                  <pre>{JSON.stringify(event.data, null, 2)}</pre>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function ArtifactsPage({ initialWellId }: { initialWellId: string }) {
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([])
  const [kind, setKind] = useState('')
  const [agentId, setAgentId] = useState('')
  const [wellId, setWellId] = useState(initialWellId)
  const [selected, setSelected] = useState<ArtifactInfo | null>(null)
  const [error, setError] = useState('')

  const load = async (nextKind = kind, nextAgentId = agentId, nextWellId = wellId) => {
    setError('')
    try {
      const data = await fetchArtifacts(nextKind, nextWellId.trim(), nextAgentId.trim())
      setArtifacts(data.artifacts)
      setSelected(prev => prev && data.artifacts.some(a => a.id === prev.id) ? prev : data.artifacts[0] ?? null)
    } catch (e) {
      setError(String(e))
    }
  }

  useEffect(() => { setWellId(initialWellId); void load('', '', initialWellId) }, [initialWellId])

  const handleDeleteArtifact = async (item: ArtifactInfo) => {
    if (!window.confirm(`确认删除产物 ${item.filename}？会同时清理对应 metadata；Trace 和任务记录不会删除。`)) return
    try {
      await deleteArtifact(item.kind, item.filename)
      await load(kind, agentId, wellId)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="domain-grid artifact-grid">
      <div className="route-card">
        <div className="route-card-header">
          <span>产物列表</span>
          <button className="mgr-btn secondary" onClick={() => void load()}>刷新</button>
        </div>
        <div className="history-search">
          <select value={kind} onChange={e => { setKind(e.target.value); void load(e.target.value) }}>
            <option value="">全部</option>
            <option value="chart">图表</option>
            <option value="code">代码</option>
          </select>
          <input
            placeholder="按井 ID 过滤"
            value={wellId}
            onChange={e => setWellId(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void load(kind, agentId, wellId) }}
          />
          <input
            placeholder="按 Agent ID 过滤"
            value={agentId}
            onChange={e => setAgentId(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void load(kind, agentId) }}
          />
          <button className="mgr-btn secondary" onClick={() => void load(kind, agentId, wellId)}>筛选</button>
        </div>
        {error && <div className="detail-action-error">{error}</div>}
        <div className="route-list">
          {artifacts.length === 0 && <div className="empty-hint">暂无生成产物。</div>}
          {artifacts.map(item => (
            <button
              key={item.id}
              className={`route-list-item ${selected?.id === item.id ? 'active' : ''}`}
              onClick={() => setSelected(item)}
            >
              <div>
                <strong>{item.filename}</strong>
                <p>{item.kind} · {(item.size / 1024).toFixed(1)}KB · agent {item.agent_id || '—'} · well {item.well_id || '—'}</p>
              </div>
              <span className="pill">{item.kind}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="route-card task-detail-card">
        {!selected && <div className="empty-hint">选择产物查看预览。</div>}
        {selected && (
          <>
            <h3>{selected.filename}</h3>
            <div className="detail-meta">
              <span className="pill ok">{selected.kind}</span>
              <span>task {selected.task_id || '—'}</span>
              <span>trace {selected.trace_id || '—'}</span>
              <span>agent {selected.agent_id || '—'}</span>
              <span>well {selected.well_id || '—'}</span>
              <span>sha256 {selected.sha256 ? selected.sha256.slice(0, 12) : '—'}</span>
            </div>
            <div className="detail-actions">
              <a className="action-btn primary" href={selected.download_url}>下载</a>
              <button className="action-btn danger" onClick={() => void handleDeleteArtifact(selected)}>删除</button>
              {selected.trace_id && (
                <button
                  className="action-btn"
                  onClick={() => {
                    window.history.pushState({}, '', `${currentBasePath()}/trace/${selected.trace_id}`)
                    window.dispatchEvent(new PopStateEvent('popstate'))
                  }}
                >
                  打开 Trace
                </button>
              )}
            </div>
            {selected.kind === 'chart' ? (
              <div className="artifact-preview">
                <img src={selected.url} alt={selected.filename} />
              </div>
            ) : (
              <div className="detail-section">
                <label>Code Preview</label>
                <pre>{selected.preview || '—'}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

interface DomainEntityRow {
  id: string
  label: string
  detail: string
  onEdit: () => void
  onDelete: () => void
}

function DomainEntityList({
  title,
  wells,
  filterWellId,
  onFilter,
  rows,
}: {
  title: string
  wells: Well[]
  filterWellId: string
  onFilter: (wellId: string) => void
  rows: DomainEntityRow[]
}) {
  return (
    <div className="route-card">
      <div className="route-card-header">
        <span>{title}</span>
        <span className="pill">{rows.length}</span>
      </div>
      <div className="history-search domain-filter">
        <select value={filterWellId} onChange={e => onFilter(e.target.value)}>
          <option value="">全部井</option>
          {wells.map(well => <option key={well.id} value={well.id}>{well.name}</option>)}
        </select>
      </div>
      <div className="route-list">
        {rows.length === 0 && <div className="empty-hint">当前筛选下暂无记录。</div>}
        {rows.map(row => (
          <div key={row.id} className="route-list-item">
            <div><strong>{row.label}</strong><p>{row.detail}</p></div>
            <div className="mgr-actions">
              <button className="mgr-btn secondary" onClick={row.onEdit}>详情/编辑</button>
              <button className="mgr-btn danger" onClick={row.onDelete}>删除</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function DomainMiniList({ title, rows }: { title: string; rows: string[] }) {
  return (
    <>
      <div className="mgr-section-title">{title}</div>
      <div className="mgr-list">
        {rows.length === 0 && <div className="empty-hint">暂无{title}。</div>}
        {rows.map((row, idx) => (
          <div className="mgr-item" key={`${title}-${idx}`}>
            <div className="mgr-item-main"><p>{row}</p></div>
          </div>
        ))}
      </div>
    </>
  )
}

function ChatHistoryPanel({ onRestore }: { onRestore: (session: ChatSessionDetail) => void }) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [query, setQuery] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async (q = query, archived = showArchived) => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchChatSessions(q, 20, {
        includeArchived: archived,
        archivedOnly: archived,
      })
      setSessions(data.sessions)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load('')
  }, [])

  const handleRestore = async (threadId: string) => {
    try {
      onRestore(await fetchChatSession(threadId))
    } catch (e) {
      setError(String(e))
    }
  }

  const handleExport = async (threadId: string) => {
    try {
      const text = await exportChatSession(threadId)
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `boetclaw-session-${threadId}.md`
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleArchiveToggle = async (session: ChatSessionSummary) => {
    try {
      if (session.archived) {
        await unarchiveChatSession(session.thread_id)
      } else {
        await archiveChatSession(session.thread_id)
      }
      await load(query, showArchived)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (session: ChatSessionSummary) => {
    if (!window.confirm(`确认删除会话 ${session.title || session.thread_id}？该操作只删除本地会话历史，不会清理 Trace 或 checkpoint。`)) return
    try {
      await deleteChatSession(session.thread_id)
      await load(query, showArchived)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="chat-history-panel">
      <div className="panel-header compact">
        <div className="panel-title">
          <Activity size={15} />
          <span>会话历史</span>
        </div>
        <button className="icon-btn" onClick={() => void load()} title="刷新">
          {loading ? '...' : '↻'}
        </button>
      </div>
      <div className="history-search">
        <input
          placeholder="搜索 thread / 内容"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') void load(query)
          }}
        />
        <button className="mgr-btn secondary" onClick={() => void load(query)}>搜索</button>
      </div>
      <label className="history-archived-toggle">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={e => {
            const next = e.target.checked
            setShowArchived(next)
            void load(query, next)
          }}
        />
        仅显示已归档
      </label>
      {error && <div className="detail-action-error">{error}</div>}
      <div className="history-list">
        {sessions.length === 0 && (
          <div className="empty-hint">{showArchived ? '暂无已归档会话。' : '暂无会话记录。'}</div>
        )}
        {sessions.map(session => (
          <div className="history-item" key={session.thread_id}>
            <button onClick={() => void handleRestore(session.thread_id)}>
              <strong>{session.title || session.thread_id}</strong>
              <span>
                {session.thread_id.slice(0, 8)} · {session.message_count} messages
                {session.archived ? ' · 已归档' : ''}
              </span>
            </button>
            <button className="history-export" onClick={() => void handleExport(session.thread_id)}>导出</button>
            <button className="history-export" onClick={() => void handleArchiveToggle(session)}>
              {session.archived ? '取消归档' : '归档'}
            </button>
            <button className="history-export danger" onClick={() => void handleDelete(session)}>删除</button>
          </div>
        ))}
      </div>
    </div>
  )
}

function TaskDetailPanel({
  taskId,
  initialTask,
  onTrace,
  onTaskUpdate,
  onClose,
}: {
  taskId: string
  initialTask: Task | null
  onTrace: (traceId: string) => void
  onTaskUpdate: (task: Task) => void
  onClose: () => void
}) {
  const [task, setTask] = useState<Task | null>(initialTask)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await fetchTask(taskId)
        setTask(data)
        onTaskUpdate(data)
      } catch (e) {
        setTask(null)
        setError(String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [taskId])

  return (
    <div className="route-card task-detail-card">
      {loading && <div className="empty-hint">加载任务详情...</div>}
      {!loading && error && <div className="empty-hint error-text">{error}</div>}
      {!loading && !error && task && (
        <TaskDetailContent
          task={task}
          onTaskUpdate={(updated) => {
            setTask(updated)
            onTaskUpdate(updated)
          }}
          onTrace={onTrace}
          onClose={onClose}
        />
      )}
    </div>
  )
}

function TaskDetailContent({
  task,
  onTaskUpdate,
  onTrace,
  onClose,
}: {
  task: Task
  onTaskUpdate: (task: Task) => void
  onTrace: (traceId: string) => void
  onClose: () => void
}) {
  const [busy, setBusy] = useState<'run' | 'cancel' | ''>('')
  const [actionError, setActionError] = useState('')
  const canCancel = task.status === 'pending' || task.status === 'running'
  const canRun = task.status !== 'running'

  const handleRun = async () => {
    setBusy('run')
    setActionError('')
    try {
      onTaskUpdate(await runTask(task.id))
    } catch (e) {
      setActionError(String(e))
    } finally {
      setBusy('')
    }
  }

  const handleCancel = async () => {
    setBusy('cancel')
    setActionError('')
    try {
      onTaskUpdate(await cancelTask(task.id))
    } catch (e) {
      setActionError(String(e))
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <h3>{task.title}</h3>
      <div className="detail-meta">
        <span className={`badge ${task.status}`}>{task.status}</span>
        <span>ID: {task.id}</span>
        {task.gateway && <span className="badge gateway">{task.gateway}</span>}
      </div>
      <div className="detail-actions">
        <button className="action-btn primary" disabled={!canRun || !!busy} onClick={() => void handleRun()}>
          {busy === 'run' ? '提交中...' : '重跑'}
        </button>
        <button className="action-btn danger" disabled={!canCancel || !!busy} onClick={() => void handleCancel()}>
          {busy === 'cancel' ? '取消中...' : '取消'}
        </button>
        {task.trace_id && (
          <button className="action-btn" onClick={() => onTrace(task.trace_id)}>
            查看 Trace
          </button>
        )}
        <button className="action-btn" onClick={onClose}>关闭</button>
      </div>
      {actionError && <div className="detail-action-error">{actionError}</div>}
      <div className="detail-section">
        <label>Prompt</label>
        <pre>{task.prompt}</pre>
      </div>
      {task.result && (
        <div className="detail-section">
          <label>Result</label>
          <pre>{task.result}</pre>
        </div>
      )}
      {task.error && (
        <div className="detail-section error">
          <label>Error</label>
          <pre>{task.error}</pre>
        </div>
      )}
      <div className="detail-section">
        <label>时间</label>
        <pre>{`created: ${new Date(task.created_at).toLocaleString('zh-CN')}\nupdated: ${new Date(task.updated_at).toLocaleString('zh-CN')}`}</pre>
      </div>
    </>
  )
}

function AgentsPage({
  currentAgent,
  selectedAgentId,
  onSwitch,
  onSelect,
  onDeleted,
}: {
  currentAgent: string
  selectedAgentId: string
  onSwitch: (agentId: string) => void
  onSelect: (agentId: string) => void
  onDeleted: (agentId: string) => void
}) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selected, setSelected] = useState<AgentInfo | null>(null)
  const [agentFiles, setAgentFiles] = useState<AgentFileInfo[]>([])
  const [agentHistory, setAgentHistory] = useState<AgentHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')

  const loadAgents = async () => {
    setLoading(true)
    try {
      const data = await fetchAgents()
      setAgents(data.agents)
    } catch {
      setAgents([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAgents()
  }, [])

  useEffect(() => {
    const loadDetail = async () => {
      setDetailLoading(true)
      setError('')
      try {
        const [detail, files, history] = await Promise.all([
          fetchAgent(selectedAgentId),
          fetchAgentFiles(selectedAgentId),
          fetchAgentHistory(selectedAgentId),
        ])
        setSelected(detail)
        setAgentFiles(files.files)
        setAgentHistory(history.history)
      } catch (e) {
        setSelected(null)
        setAgentFiles([])
        setAgentHistory([])
        setError(String(e))
      } finally {
        setDetailLoading(false)
      }
    }
    void loadDetail()
  }, [selectedAgentId])

  const handleDelete = async () => {
    if (!selected || selected.agent_id === 'default') return
    const proceed = window.confirm(
      `确认删除 Agent「${selected.agent_id}」？\n下一步将选择：仅注销 或 彻底清除。`,
    )
    if (!proceed) return
    const purge = window.confirm(
      `选择删除方式：\n\n确定 = 彻底清除（删除工作区目录与 checkpoint，不可恢复）\n取消 = 仅注销（写 tombstone，保留磁盘与 checkpoint，列表不可见）`,
    )
    setError('')
    try {
      await deleteAgent(selected.agent_id, { purge })
      await loadAgents()
      onDeleted(selected.agent_id)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="agent-workspace-grid">
      <div className="route-card">
        <div className="route-card-header">
          <span>工作区列表</span>
          <AgentSwitcher currentAgent={currentAgent} onSwitch={onSwitch} />
        </div>
        <div className="route-list">
          {loading && <div className="empty-hint">加载中...</div>}
          {!loading && agents.length === 0 && <div className="empty-hint">暂无 Agent 工作区。</div>}
          {agents.map(agent => (
            <button
              key={agent.agent_id}
              className={`route-list-item ${agent.agent_id === selectedAgentId ? 'active' : ''}`}
              onClick={() => onSelect(agent.agent_id)}
            >
              <div>
                <strong>{agent.agent_id}</strong>
                <p>{agent.root}</p>
              </div>
              <div className="route-list-meta">
                <span className={`pill ${agent.loaded ? 'ok' : 'off'}`}>{agent.loaded ? '就绪' : '未载'}</span>
                <span>{agent.skills_count} skills</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="route-card agent-detail-card">
        <div className="route-card-header">
          <span>工作区详情</span>
          <div className="mgr-actions">
            {selected && selected.agent_id !== currentAgent && (
              <button className="mgr-btn secondary" onClick={() => onSwitch(selected.agent_id)}>设为当前</button>
            )}
            <button
              className="mgr-btn danger"
              disabled={!selected || selected.agent_id === 'default'}
              onClick={() => void handleDelete()}
            >
              删除
            </button>
          </div>
        </div>
        <div className="settings-body">
          {detailLoading && <div className="empty-hint">加载详情...</div>}
          {error && <div className="empty-hint error-text">{error}</div>}
          {!detailLoading && selected && (
            <div className="agent-detail">
              <div className="agent-summary-grid">
                <div className="stat-card">
                  <div className="stat-value">{selected.loaded ? 'Ready' : 'Idle'}</div>
                  <div className="stat-label">运行时</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{selected.skills_count}</div>
                  <div className="stat-label">技能数</div>
                </div>
              </div>

              <div className="detail-section">
                <label>Workspace</label>
                <pre>{selected.root}</pre>
              </div>
              <div className="detail-section">
                <label>Files Root</label>
                <pre>{`${selected.root}${selected.root.endsWith('/') || selected.root.endsWith('\\') ? '' : '/'}files`}</pre>
              </div>
              <div className="detail-section">
                <label>Created At</label>
                <pre>{new Date(selected.created_at).toLocaleString('zh-CN')}</pre>
              </div>
              <div className="detail-section">
                <label>Config</label>
                <pre>{JSON.stringify(selected.config, null, 2)}</pre>
              </div>

              <div className="mgr-section-title">工作区技能聚合</div>
              <SkillsManager agentId={selected.agent_id} />

              <div className="mgr-section-title">运行历史与文件索引</div>
              <div className="agent-index-grid">
                <div className="mgr-list">
                  <div className="mgr-section-title">运行历史</div>
                  {agentHistory.length === 0 && <div className="empty-hint">暂无该 Agent 的任务或会话历史。</div>}
                  {agentHistory.map(item => (
                    <div className="mgr-item" key={`${item.type}-${item.id}`}>
                      <div className="mgr-item-main">
                        <h4>{item.type} · {item.title}</h4>
                        <p>{item.status} · thread {item.thread_id || '—'} · trace {item.trace_id || '—'}</p>
                        <p>{item.match_source} · {item.updated_at || '—'}</p>
                      </div>
                      <span className="pill">{item.type}</span>
                    </div>
                  ))}
                </div>
                <div className="mgr-list">
                  <div className="mgr-section-title">文件索引</div>
                  {agentFiles.length === 0 && <div className="empty-hint">files 目录暂无文件。</div>}
                  {agentFiles.map(file => (
                    <div className="mgr-item" key={file.path}>
                      <div className="mgr-item-main">
                        <h4>{file.path}</h4>
                        <p>{(file.size / 1024).toFixed(1)} KB · {new Date(file.modified_at).toLocaleString('zh-CN')}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SettingsPage({
  tab,
  agentId,
  onTabChange,
}: {
  tab: SettingsTab
  agentId: string
  onTabChange: (tab: SettingsTab) => void
}) {
  const tabs: { id: SettingsTab; label: string }[] = [
    { id: 'skills', label: '技能' },
    { id: 'providers', label: '模型' },
    { id: 'scheduler', label: '定时/心跳' },
    { id: 'plugins', label: '插件' },
    { id: 'mcp', label: 'MCP' },
    { id: 'channels', label: '渠道' },
    { id: 'security', label: '安全' },
  ]

  return (
    <div className="route-card">
      <div className="settings-tabs">
        {tabs.map(item => (
          <button
            key={item.id}
            className={tab === item.id ? 'active' : ''}
            onClick={() => onTabChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="settings-body">
        {tab === 'skills' && <SkillsManager agentId={agentId} />}
        {tab === 'providers' && <ProviderSettings />}
        {tab === 'scheduler' && <CronManager />}
        {tab === 'plugins' && <PluginsManager />}
        {tab === 'mcp' && <McpManager />}
        {tab === 'channels' && <ChannelsManager />}
        {tab === 'security' && <SecuritySettings />}
      </div>
    </div>
  )
}

function SecuritySettings() {
  const [config, setConfig] = useState<{ enabled: boolean; level: string } | null>(null)
  const [history, setHistory] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [cfg, hist] = await Promise.all([fetchGuardConfig(), fetchApprovalHistory()])
      setConfig(cfg)
      setHistory(hist.approvals)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleLevelChange = async (level: string) => {
    setSaving(true)
    setError('')
    try {
      setConfig(await updateGuardConfig(level))
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="mgr-section-title">ToolGuard 策略</div>
      <div className="security-config">
        <div>
          <h4><ShieldAlert size={14} /> 工具执行保护</h4>
          <p>当前状态：{config?.enabled ? '已启用' : '已关闭'}；级别决定工具调用是否需要人工审批。</p>
        </div>
        <select
          value={config?.level ?? 'smart'}
          disabled={loading || saving}
          onChange={e => void handleLevelChange(e.target.value)}
        >
          <option value="strict">strict</option>
          <option value="smart">smart</option>
          <option value="auto">auto</option>
          <option value="off">off</option>
        </select>
      </div>
      {error && <div className="detail-action-error">{error}</div>}

      <div className="mgr-section-title">待审批工具调用</div>
      <ApprovalCard />

      <div className="mgr-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>审批历史</span>
        <button className="mgr-btn secondary" onClick={() => void load()} disabled={loading}>刷新</button>
      </div>
      <div className="approval-history">
        {history.length === 0 && <div className="empty-hint">暂无审批历史。</div>}
        {history.map(req => (
          <div className="approval-history-item" key={req.id}>
            <div>
              <h4>{req.tool}</h4>
              <p>{new Date(req.created_at).toLocaleString('zh-CN')} · thread {req.thread_id || '—'}</p>
              {req.findings.length > 0 && (
                <p>{req.findings.map(f => `${f.severity}:${f.message}`).join('；')}</p>
              )}
              {!req.execution_ref && <p>缺少执行引用，此历史记录不可恢复。</p>}
              {req.error && <p className="detail-action-error">{req.error}</p>}
            </div>
            <span className={`pill ${req.status === 'approved' ? 'ok' : req.status === 'pending' ? 'off' : ''}`}>
              {req.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
