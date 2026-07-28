import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Activity,
  BookOpen,
  Bot,
  ListTodo,
  LogOut,
  Menu,
  MessageSquare,
  Settings,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import ChatPanel from './components/ChatPanel'
import ModelSelector, { type ModelSelection } from './components/ModelSelector'
import RunMetricsCard from './components/RunMetricsCard'
import type { RunMetricsSummary } from './services/api'
import TaskMonitor from './components/TaskMonitor'
import SidePanel from './components/SidePanel'
import AgentSwitcher from './components/AgentSwitcher'
import AgentWorkspacePage from './components/AgentWorkspacePage'
import ConsoleModal from './components/ConsoleModal'
import ApprovalCard from './components/ApprovalCard'
import SkillsManager from './components/SkillsManager'
import ProviderSettings from './components/ProviderSettings'
import CronManager from './components/CronManager'
import PluginsManager from './components/PluginsManager'
import McpManager from './components/McpManager'
import ChannelsManager from './components/ChannelsManager'
import MemoryManager from './components/MemoryManager'
import MemoryContextCard from './components/MemoryContextCard'
import KnowledgeBasePage from './components/KnowledgeBasePage'
import {
  cancelTask,
  archiveChatSession,
  deleteChatSession,
  exportChatSession,
  unarchiveChatSession,
  fetchApprovalHistory,
  fetchConsoleAuthStatus,
  fetchChatSession,
  fetchChatSessions,
  fetchGuardConfig,
  fetchStats,
  fetchTask,
  fetchTraceTimeline,
  loginConsole,
  logoutConsole,
  runTask,
  updateGuardConfig,
  type ApprovalRequest,
  type ChatMessage,
  type ChatSessionDetail,
  type ChatSessionSummary,
  type ConsoleAuthStatus,
  type Task,
  type TraceTimeline,
  type MemoryContextSummary,
} from './services/api'
import './App.css'

type SettingsTab = 'skills' | 'providers' | 'scheduler' | 'plugins' | 'mcp' | 'channels' | 'security' | 'memory'

interface AppRoute {
  page: 'chat' | 'tasks' | 'agents' | 'knowledge' | 'trace' | 'settings' | 'removed' | 'not-found'
  taskId?: string
  agentId?: string
  traceId?: string
  settingsTab?: SettingsTab
  removedPath?: string
}

const NAV_ITEMS: {
  path: string
  label: string
  match: AppRoute['page'][]
  icon: typeof MessageSquare
}[] = [
  { path: '/chat', label: '对话工作台', match: ['chat'], icon: MessageSquare },
  { path: '/tasks', label: '任务与追踪', match: ['tasks', 'trace'], icon: ListTodo },
  { path: '/agents', label: 'Agent 工作区', match: ['agents'], icon: Bot },
  { path: '/knowledge', label: '知识库', match: ['knowledge'], icon: BookOpen },
  { path: '/settings/skills', label: '设置', match: ['settings'], icon: Settings },
]

function isRemovedLegacyPath(path: string): boolean {
  if (path === '/wells' || path.startsWith('/wells/')) return true
  if (path === '/reports' || path === '/params') return true
  if (path === '/las/import' || path === '/artifacts') return true
  return false
}

function routeTitle(route: AppRoute): string {
  switch (route.page) {
    case 'chat':
      return '对话工作台'
    case 'tasks':
      return route.taskId ? `任务 ${route.taskId}` : '任务与追踪'
    case 'agents':
      return 'Agent 工作区'
    case 'knowledge':
      return '知识库'
    case 'trace':
      return route.traceId ? `Trace ${route.traceId.slice(0, 8)}` : '追踪'
    case 'settings':
      return '设置'
    case 'removed':
      return '页面已移除'
    default:
      return '页面不存在'
  }
}

function isNavActive(match: AppRoute['page'][], page: AppRoute['page']) {
  return match.includes(page)
}

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
  const path = stripUiBase(pathname.split('?', 2)[0]).replace(/\/+$/, '') || '/'
  if (isRemovedLegacyPath(path)) return { page: 'removed', removedPath: path }
  if (path === '/' || path === '/chat') return { page: 'chat' }
  if (path === '/tasks') return { page: 'tasks' }
  if (path.startsWith('/tasks/')) {
    return { page: 'tasks', taskId: decodeURIComponent(path.slice('/tasks/'.length)) }
  }
  if (path === '/agents') return { page: 'agents' }
  if (path.startsWith('/agents/')) {
    return { page: 'agents', agentId: decodeURIComponent(path.slice('/agents/'.length)) }
  }
  if (path === '/knowledge') return { page: 'knowledge' }
  if (path === '/trace') return { page: 'trace' }
  if (path.startsWith('/trace/')) {
    return { page: 'trace', traceId: decodeURIComponent(path.slice('/trace/'.length)) }
  }
  if (path === '/settings') return { page: 'settings', settingsTab: 'skills' }
  if (path.startsWith('/settings/')) {
    const raw = path.slice('/settings/'.length)
    const allowed: SettingsTab[] = ['skills', 'providers', 'scheduler', 'plugins', 'mcp', 'channels', 'security', 'memory']
    return {
      page: 'settings',
      settingsTab: allowed.includes(raw as SettingsTab) ? raw as SettingsTab : 'skills',
    }
  }
  return { page: 'not-found' }
}

export { parseRoute, isRemovedLegacyPath }

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
  const [navOpen, setNavOpen] = useState(false)
  const [agentCreateTrigger, setAgentCreateTrigger] = useState(0)
  const [chatModelSelection, setChatModelSelection] = useState<ModelSelection | null>(null)
  const [composerAttachmentCount, setComposerAttachmentCount] = useState(0)
  const [composerAttachments, setComposerAttachments] = useState<Array<{ kind: string }>>([])
  const [latestRunMetrics, setLatestRunMetrics] = useState<RunMetricsSummary | null>(null)
  const [runMetricsLoading, setRunMetricsLoading] = useState(false)
  const [memoryContext, setMemoryContext] = useState<MemoryContextSummary | null>(null)

  const handleComposerAttachmentsChange = useCallback((count: number, items: Array<{ kind: string }>) => {
    setComposerAttachmentCount(count)
    setComposerAttachments(items)
  }, [])

  const handleRunMetrics = useCallback((metrics: RunMetricsSummary) => {
    setLatestRunMetrics(metrics)
    setRunMetricsLoading(false)
  }, [])

  const handleRunStarted = useCallback(() => {
    setRunMetricsLoading(true)
  }, [])

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
          <Sparkles size={28} />
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
      {navOpen && <button className="nav-backdrop" aria-label="关闭导航" onClick={() => setNavOpen(false)} />}
      <aside className={`global-sidebar${navOpen ? ' open' : ''}`} aria-label="全局导航">
        <div className="sidebar-brand">
          <div className="brand-mark">
            <Sparkles size={18} />
            <span className="brand-name">BOETCLAW</span>
          </div>
          <span className="brand-status" title="本地实例在线">LOCAL · ONLINE</span>
        </div>
        <nav className="global-nav">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon
            const active = isNavActive(item.match, routePage)
            return (
              <button
                key={item.path}
                type="button"
                className={`global-nav-item${active ? ' active' : ''}`}
                aria-current={active ? 'page' : undefined}
                title={item.label}
                onClick={() => {
                  navigate(item.path)
                  setNavOpen(false)
                }}
              >
                <Icon size={16} aria-hidden />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>
        <div className="sidebar-footer">
          <span className="sidebar-footnote">单机 Agent 控制台</span>
          {authStatus?.login_required && (
            <button
              type="button"
              className="sidebar-logout"
              onClick={async () => {
                await logoutConsole()
                setAuthStatus({ login_required: true, authenticated: false })
              }}
            >
              <LogOut size={14} />
              <span>退出登录</span>
            </button>
          )}
        </div>
      </aside>

      <div className="app-shell">
        <header className="app-topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="nav-toggle"
              aria-label={navOpen ? '收起导航' : '展开导航'}
              onClick={() => setNavOpen(v => !v)}
            >
              {navOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
            <div className="topbar-title-wrap">
              <h1 className="topbar-title">{routeTitle(route)}</h1>
              {routePage === 'chat' && (
                <p className="topbar-subtitle">多模态 Agent 协作空间</p>
              )}
            </div>
          </div>
          <div className="topbar-actions">
            {routePage === 'chat' && (
              <ModelSelector
                value={chatModelSelection}
                onChange={setChatModelSelection}
                disabled={false}
                pendingAttachments={composerAttachments}
              />
            )}
            {threadId && <span className="thread-badge">Thread: {threadId.slice(0, 8)}</span>}
            {effectiveTraceId && (
              <button
                type="button"
                className="trace-badge trace-link"
                onClick={() => navigate(`/trace/${effectiveTraceId}`)}
              >
                Trace: {effectiveTraceId.slice(0, 8)}
              </button>
            )}
            <AgentSwitcher currentAgent={agentId} onSwitch={handleSwitchAgent} />
            {routePage === 'agents' && (
              <button
                type="button"
                className="topbar-primary"
                aria-label="＋ 新建 Agent"
                onClick={() => setAgentCreateTrigger(v => v + 1)}
              >
                ＋ 新建 Agent
              </button>
            )}
          </div>
        </header>

        <div className="app-content">
      {routePage === 'chat' && (
        <main className="chat-workspace">
          <ChatHistoryPanel
            onNewChat={() => {
              setThreadId(null)
              setRestoredMessages([])
              setHistoryVersion(v => v + 1)
              setActiveTraceId(null)
              navigate('/chat')
            }}
            onRestore={(session) => {
              setThreadId(session.thread_id)
              setAgentId(session.agent_id || 'default')
              setActiveTraceId(session.last_trace_id || null)
              setRestoredMessages(session.messages)
              setHistoryVersion(v => v + 1)
              navigate('/chat')
            }}
          />
          <section className="chat-main">
            <ChatPanel
              threadId={threadId}
              agentId={agentId}
              onThreadId={setThreadId}
              onTraceUpdate={(traceId) => setActiveTraceId(traceId)}
              onRunMetrics={handleRunMetrics}
              onRunStarted={handleRunStarted}
              initialMessages={restoredMessages}
              historyVersion={historyVersion}
              modelSelection={chatModelSelection}
              onComposerAttachmentsChange={handleComposerAttachmentsChange}
              onMemoryContext={setMemoryContext}
            />
          </section>
          <aside className="run-context" aria-label="运行上下文">
            <div className="context-card">
              <div className="run-context-header">运行上下文</div>
              <dl className="context-kv mono">
                <div><dt>状态</dt><dd>{threadId ? 'READY' : '待命'}</dd></div>
                <div><dt>Agent</dt><dd>{agentId}</dd></div>
                <div><dt>模型</dt><dd>{chatModelSelection ? `${chatModelSelection.provider}/${chatModelSelection.model}` : '默认'}</dd></div>
                <div><dt>Trace</dt><dd>{effectiveTraceId ? effectiveTraceId.slice(0, 8) : '—'}</dd></div>
                <div><dt>附件</dt><dd>{composerAttachmentCount} 个</dd></div>
              </dl>
            </div>
            <MemoryContextCard summary={memoryContext} />
            <RunMetricsCard
              metrics={latestRunMetrics}
              loading={runMetricsLoading}
              modelLabel={
                latestRunMetrics?.model && latestRunMetrics?.provider
                  ? `${latestRunMetrics.model} · ${latestRunMetrics.provider}`
                  : chatModelSelection?.label
              }
            />
            <div className="context-card">
              <div className="run-context-header">能力与兼容性</div>
              <ul className="context-boundary-list">
                <li>浏览器不支持语音时自动禁用</li>
                <li>文件类型或大小不符时阻止发送</li>
                <li>模型切换仅影响后续消息</li>
                <li>文件夹保留相对路径</li>
              </ul>
            </div>
            <ApprovalCard />
            <div className="run-context-panel">
              <SidePanel activeTraceId={effectiveTraceId} />
            </div>
            <p className="context-footnote">附件仅发送到当前 Agent 工作区</p>
          </aside>
        </main>
      )}

      {routePage === 'tasks' && (
        <main className="route-main">
          <PageHeader
            icon={<ListTodo size={18} />}
            title={route.taskId ? `任务 ${route.taskId}` : '任务与追踪'}
            description="查看、创建、筛选并管理 Agent 后台任务；可从任务详情重跑、取消或跳转到关联 Trace。"
          />
          <div className="route-grid two-columns tasks-layout">
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
              <div className="route-panel tall run-context-standalone">
                <div className="run-context-header">Trace 预览</div>
                <SidePanel activeTraceId={effectiveTraceId} />
              </div>
            )}
          </div>
        </main>
      )}

      {routePage === 'agents' && (
        <main className="route-main agent-route-main">
          <PageHeader
            icon={<Bot size={18} />}
            title={route.agentId ? `Agent ${route.agentId}` : 'Agent 工作区'}
            description="搜索、创建与管理 Agent 工作区；查看模型、技能、checkpoint 与运行状态，执行打开、归档或彻底清理。"
          />
          <AgentWorkspacePage
            currentAgent={agentId}
            selectedAgentId={route.agentId ?? agentId}
            createTrigger={agentCreateTrigger}
            onSwitch={handleSwitchAgent}
            onSelect={(id) => navigate(`/agents/${id}`)}
            onOpenChat={(id) => {
              handleSwitchAgent(id)
              navigate('/chat')
            }}
            onDeleted={(id) => {
              if (id === agentId) handleSwitchAgent('default')
              navigate('/agents/default')
            }}
          />
        </main>
      )}

      {routePage === 'knowledge' && (
        <main className="route-main agent-route-main">
          <PageHeader
            icon={<BookOpen size={18} />}
            title="知识库"
            description="创建长期知识库、批量上传文档、管理解析状态，并在 Agent 工作区绑定默认启用的库。"
          />
          <KnowledgeBasePage agentId={agentId} />
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

      {routePage === 'removed' && (
        <main className="route-main">
          <div className="page-state error">
            <div className="page-state-indicator" aria-hidden />
            <h2>页面已移除</h2>
            <p>
              路径 <code className="mono">{route.removedPath || '—'}</code> 对应的钻井领域模块（井、日报、参数、LAS、产物）已从产品界面移除。
              后端 API 与历史数据仍保留以维持兼容。
            </p>
            <div className="page-state-actions">
              <button type="button" className="primary-btn" onClick={() => navigate('/chat')}>
                返回对话工作台
              </button>
              <button type="button" className="mgr-btn secondary" onClick={() => navigate('/agents')}>
                打开 Agent 工作区
              </button>
            </div>
          </div>
        </main>
      )}

      {routePage === 'settings' && (
        <main className="route-main">
          <PageHeader
            icon={<Settings size={18} />}
            title="设置"
            description="技能、模型 Provider、Cron/心跳、插件、渠道、长期记忆与 MCP 的统一配置中心。"
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
          <div className="page-state error">
            <div className="page-state-indicator" aria-hidden />
            <h2>页面不存在</h2>
            <p>当前路径无法匹配已知路由。可返回对话工作台或从左侧导航进入现有页面。</p>
            <button type="button" className="primary-btn" onClick={() => navigate('/chat')}>
              返回对话工作台
            </button>
          </div>
        </main>
      )}
        </div>
      </div>

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
        <span className="route-title-text">{title}</span>
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
          <Sparkles size={28} />
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
    return <div className="route-card"><div className="empty-hint">暂无 Trace。请从对话或任务打开关联 Trace。</div></div>
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

function ChatHistoryPanel({
  onRestore,
  onNewChat,
}: {
  onRestore: (session: ChatSessionDetail) => void
  onNewChat: () => void
}) {
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
      <div className="history-panel-head">
        <span className="history-panel-title">最近对话</span>
        <button type="button" className="history-new-btn" onClick={onNewChat}>＋ 新对话</button>
      </div>
      <div className="history-search">
        <input
          placeholder="⌕  搜索对话"
          value={query}
          aria-label="搜索对话"
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') void load(query)
          }}
        />
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
        {loading && sessions.length === 0 && <div className="empty-hint">正在加载会话…</div>}
        {!loading && sessions.length === 0 && (
          <div className="empty-hint">{showArchived ? '暂无已归档会话。' : '暂无会话记录。'}</div>
        )}
        {sessions.map(session => (
          <div className={`history-item${session.archived ? ' archived' : ''}`} key={session.thread_id}>
            <button type="button" className="history-item-main" onClick={() => void handleRestore(session.thread_id)}>
              <strong>{session.title || session.thread_id}</strong>
              <span className="mono">
                {session.updated_at ? new Date(session.updated_at).toLocaleString('zh-CN') : '—'}
                {' · '}{session.message_count} 条
              </span>
            </button>
            <div className="history-item-actions">
              <button type="button" className="history-export" onClick={() => void handleExport(session.thread_id)}>导出</button>
              <button type="button" className="history-export" onClick={() => void handleArchiveToggle(session)}>
                {session.archived ? '取消归档' : '归档'}
              </button>
              <button type="button" className="history-export danger" onClick={() => void handleDelete(session)}>删除</button>
            </div>
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
    { id: 'providers', label: '模型 Provider' },
    { id: 'scheduler', label: 'Cron 与心跳' },
    { id: 'plugins', label: '插件' },
    { id: 'channels', label: '渠道' },
    { id: 'mcp', label: 'MCP' },
    { id: 'memory', label: '长期记忆' },
    { id: 'security', label: '安全' },
  ]

  const active = tabs.find(item => item.id === tab) ?? tabs[0]
  const [health, setHealth] = useState<{ ok: boolean; events: number; tasks: number; error: string }>({
    ok: false,
    events: 0,
    tasks: 0,
    error: '',
  })

  useEffect(() => {
    let cancelled = false
    fetchStats()
      .then(stats => {
        if (cancelled) return
        const taskTotal = Object.values(stats.tasks || {}).reduce((sum, n) => sum + n, 0)
        setHealth({ ok: true, events: stats.trace_events, tasks: taskTotal, error: '' })
      })
      .catch(e => {
        if (cancelled) return
        setHealth({ ok: false, events: 0, tasks: 0, error: e instanceof Error ? e.message : String(e) })
      })
    return () => { cancelled = true }
  }, [tab])

  return (
    <div className="settings-workspace">
      <aside className="settings-nav" aria-label="配置中心">
        <div className="settings-nav-title">配置中心</div>
        {tabs.map(item => (
          <button
            key={item.id}
            type="button"
            className={tab === item.id ? 'active' : ''}
            onClick={() => onTabChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </aside>
      <section className="settings-form-panel route-card">
        <div className="settings-form-header">
          <h3>{active.label}</h3>
          <p>配置写入本地环境；密钥不明文展示，危险操作需二次确认。</p>
        </div>
        <div className="settings-body">
          {tab === 'skills' && <SkillsManager agentId={agentId} />}
          {tab === 'providers' && <ProviderSettings />}
          {tab === 'scheduler' && <CronManager />}
          {tab === 'plugins' && <PluginsManager />}
          {tab === 'mcp' && <McpManager />}
          {tab === 'channels' && <ChannelsManager />}
          {tab === 'memory' && <MemoryManager agentId={agentId} />}
          {tab === 'security' && <SecuritySettings />}
        </div>
      </section>
      <aside className="settings-side">
        <div className="route-card settings-health">
          <div className="route-card-header"><span>运行健康</span></div>
          <div className="health-list">
            <div>
              <span>API 服务</span>
              <span className={`status-text ${health.ok ? 'success' : 'warning'}`}>
                {health.ok ? '正常' : (health.error ? '异常' : '检查中')}
              </span>
            </div>
            <div>
              <span>Trace 事件</span>
              <span className="status-text info mono">{health.ok ? health.events : '—'}</span>
            </div>
            <div>
              <span>任务总量</span>
              <span className="status-text info mono">{health.ok ? health.tasks : '—'}</span>
            </div>
            <div>
              <span>监控接口</span>
              <span className={`status-text ${health.ok ? 'success' : 'warning'}`}>
                {health.ok ? '已连通' : (health.error || '未连通')}
              </span>
            </div>
          </div>
        </div>
        <div className="route-card settings-danger">
          <div className="route-card-header"><span className="danger-title">危险操作</span></div>
          <p id="settings-clear-local-data-desc">
            清理本地运行数据将删除会话、Trace 与 checkpoint，且不可撤销。当前版本暂未开放此功能，请通过运维流程处理。
          </p>
          <button
            type="button"
            className="mgr-btn danger"
            disabled
            aria-label="清理本地数据，暂未开放"
            aria-describedby="settings-clear-local-data-desc"
          >
            暂未开放
          </button>
        </div>
      </aside>
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
