import { useEffect, useMemo, useState } from 'react'
import {
  createAgent,
  deleteAgent,
  fetchAgent,
  fetchAgentFiles,
  fetchAgentHistory,
  fetchAgents,
  fetchApprovals,
  fetchDefaultProviderConfig,
  fetchMonitorHealth,
  fetchSkills,
  fetchStats,
  fetchTasks,
  type AgentFileInfo,
  type AgentHistoryItem,
  type AgentInfo,
} from '../services/api'
import SkillsManager from './SkillsManager'

interface AgentWorkspacePageProps {
  currentAgent: string
  selectedAgentId: string
  createTrigger?: number
  onSwitch: (agentId: string) => void
  onSelect: (agentId: string) => void
  onDeleted: (agentId: string) => void
  onOpenChat: (agentId: string) => void
}

function formatRelativeTime(iso: string | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diffMs = Date.now() - then
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours} 小时前`
  return new Date(iso).toLocaleString('zh-CN')
}

function agentRowSubtitle(agent: AgentInfo): string {
  const desc = typeof agent.config?.description === 'string' ? agent.config.description : ''
  if (desc) return desc
  if (agent.agent_id === 'default') return '主工作区'
  return agent.loaded ? '已加载' : '未加载'
}

function lifecycleLabel(agent: AgentInfo, history: AgentHistoryItem[]): { text: string; tone: 'online' | 'running' | 'idle' } {
  const activeTask = history.find(h => h.type === 'task' && (h.status === 'running' || h.status === 'pending'))
  if (activeTask) return { text: '运行中', tone: 'running' }
  if (agent.loaded) return { text: '在线', tone: 'online' }
  return { text: '空闲', tone: 'idle' }
}

function resolveModelLabel(agent: AgentInfo, defaultModel: string | null): string {
  const cfg = agent.config || {}
  const model = typeof cfg.model === 'string' ? cfg.model : ''
  const provider = typeof cfg.provider === 'string' ? cfg.provider : ''
  if (model && provider) return `${provider}/${model}`
  if (model) return model
  if (defaultModel) return defaultModel
  return '未配置（使用全局默认）'
}

function checkpointLabel(backend: string | undefined): string {
  if (!backend) return '不可用'
  if (backend === 'sqlite') return 'SQLite'
  if (backend === 'memory') return 'Memory（不持久）'
  return backend
}

export default function AgentWorkspacePage({
  currentAgent,
  selectedAgentId,
  createTrigger = 0,
  onSwitch,
  onSelect,
  onDeleted,
  onOpenChat,
}: AgentWorkspacePageProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selected, setSelected] = useState<AgentInfo | null>(null)
  const [agentFiles, setAgentFiles] = useState<AgentFileInfo[]>([])
  const [agentHistory, setAgentHistory] = useState<AgentHistoryItem[]>([])
  const [enabledSkills, setEnabledSkills] = useState<number | null>(null)
  const [defaultModel, setDefaultModel] = useState<string | null>(null)
  const [checkpointBackend, setCheckpointBackend] = useState<string | undefined>()
  const [runtime, setRuntime] = useState({
    activeTasks: 0,
    pendingApprovals: 0,
    traceEvents: 0,
    recentErrors: 0,
    loading: true,
    error: '',
  })
  const [query, setQuery] = useState('')
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [actionError, setActionError] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newAgentId, setNewAgentId] = useState('')

  const loadAgents = async () => {
    setListLoading(true)
    setListError('')
    try {
      const data = await fetchAgents()
      setAgents(data.agents)
    } catch (e) {
      setAgents([])
      setListError(e instanceof Error ? e.message : String(e))
    } finally {
      setListLoading(false)
    }
  }

  const loadRuntime = async () => {
    setRuntime(prev => ({ ...prev, loading: true, error: '' }))
    try {
      const [stats, tasks, approvals] = await Promise.all([
        fetchStats(),
        fetchTasks(),
        fetchApprovals(),
      ])
      const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'pending').length
      const recentErrors = tasks.filter(t => t.status === 'failed').length
      setRuntime({
        activeTasks,
        pendingApprovals: approvals.pending.length,
        traceEvents: stats.trace_events,
        recentErrors,
        loading: false,
        error: '',
      })
    } catch (e) {
      setRuntime(prev => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : String(e),
      }))
    }
  }

  useEffect(() => {
    void loadAgents()
    void loadRuntime()
    fetchDefaultProviderConfig()
      .then(cfg => setDefaultModel(cfg.model ? `${cfg.provider}/${cfg.model}` : cfg.provider || null))
      .catch(() => setDefaultModel(null))
    fetchMonitorHealth()
      .then(health => setCheckpointBackend(health.checkpoint?.backend))
      .catch(() => setCheckpointBackend(undefined))
  }, [])

  useEffect(() => {
    if (createTrigger > 0) setShowCreateForm(true)
  }, [createTrigger])

  const loadDetail = async (agentId: string) => {
    setDetailLoading(true)
    setDetailError('')
    setActionError('')
    setEnabledSkills(null)
    try {
      const [detail, files, history, skills] = await Promise.all([
        fetchAgent(agentId),
        fetchAgentFiles(agentId),
        fetchAgentHistory(agentId),
        fetchSkills(agentId).catch(() => ({ pool: [], workspace: [] })),
      ])
      setSelected(detail)
      setAgentFiles(files.files)
      setAgentHistory(history.history)
      setEnabledSkills(skills.workspace.filter(s => s.enabled).length)
    } catch (e) {
      setSelected(null)
      setAgentFiles([])
      setAgentHistory([])
      setDetailError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadDetail(selectedAgentId)
  }, [selectedAgentId])

  const filteredAgents = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return agents
    return agents.filter(agent =>
      [agent.agent_id, agent.root, agentRowSubtitle(agent)].join(' ').toLowerCase().includes(q),
    )
  }, [agents, query])

  const latestActivity = agentHistory[0]?.updated_at
  const lifecycle = selected ? lifecycleLabel(selected, agentHistory) : null

  const handleCreate = async () => {
    const id = newAgentId.trim()
    if (!id) {
      setActionError('请输入 Agent ID')
      return
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) {
      setActionError('Agent ID 仅支持字母、数字、下划线与连字符')
      return
    }
    setCreating(true)
    setActionError('')
    try {
      await createAgent(id)
      setNewAgentId('')
      setShowCreateForm(false)
      await loadAgents()
      onSelect(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  const handleArchive = async () => {
    if (!selected || selected.agent_id === 'default') return
    if (!window.confirm(`确认归档 Agent「${selected.agent_id}」？\n将写入 tombstone 并从列表隐藏，checkpoint 与磁盘数据保留。`)) return
    setActionError('')
    try {
      await deleteAgent(selected.agent_id, { purge: false })
      await loadAgents()
      onDeleted(selected.agent_id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handlePurge = async () => {
    if (!selected || selected.agent_id === 'default') return
    if (!window.confirm(`确认彻底清理 Agent「${selected.agent_id}」？\n此操作将删除工作区目录与 checkpoint，不可恢复。`)) return
    if (!window.confirm('最后确认：彻底清理后无法 resume 历史会话，是否继续？')) return
    setActionError('')
    try {
      await deleteAgent(selected.agent_id, { purge: true })
      await loadAgents()
      onDeleted(selected.agent_id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const capabilities = [
    { label: '对话与计划', available: true },
    { label: '安全工具调用', available: true },
    { label: '技能与插件', available: (selected?.skills_count ?? 0) > 0 || enabledSkills !== null },
    { label: '任务与 Trace', available: agentHistory.some(h => h.type === 'task') || runtime.traceEvents > 0 },
  ]

  return (
    <div className="agent-workspace-page">
      <div className="agent-list-panel route-card">
        <div className="route-card-header agent-list-header">
          <span>Agent</span>
          <button type="button" className="mgr-btn secondary compact" onClick={() => void loadAgents()} disabled={listLoading}>
            {listLoading ? '…' : '刷新'}
          </button>
        </div>
        <div className="agent-search">
          <input
            type="search"
            placeholder="搜索 Agent…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="搜索 Agent"
          />
        </div>
        {showCreateForm && (
          <div className="agent-create-inline mgr-form">
            <input
              placeholder="新 Agent ID"
              value={newAgentId}
              onChange={e => setNewAgentId(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void handleCreate() }}
              aria-label="新 Agent ID"
              autoFocus
            />
            <button type="button" className="mgr-btn" disabled={creating} onClick={() => void handleCreate()}>
              {creating ? '创建中…' : '创建'}
            </button>
            <button type="button" className="mgr-btn secondary" onClick={() => { setShowCreateForm(false); setNewAgentId('') }}>
              取消
            </button>
          </div>
        )}
        {listError && <div className="detail-action-error" role="alert">{listError}</div>}
        <div className="agent-list" role="listbox" aria-label="Agent 列表">
          {listLoading && agents.length === 0 && (
            <div className="page-state loading compact">
              <div className="page-state-indicator" aria-hidden />
              <p>正在加载 Agent…</p>
            </div>
          )}
          {!listLoading && filteredAgents.length === 0 && (
            <div className="page-state empty compact">
              <div className="page-state-indicator" aria-hidden />
              <p>{query ? '没有匹配的 Agent。' : '暂无 Agent 工作区。'}</p>
            </div>
          )}
          {filteredAgents.map(agent => {
            const rowLife = lifecycleLabel(agent, agent.agent_id === selectedAgentId ? agentHistory : [])
            return (
              <button
                key={agent.agent_id}
                type="button"
                role="option"
                aria-selected={agent.agent_id === selectedAgentId}
                className={`agent-list-row${agent.agent_id === selectedAgentId ? ' active' : ''}`}
                onClick={() => onSelect(agent.agent_id)}
              >
                <span className="agent-list-id mono">{agent.agent_id}</span>
                <span className={`agent-list-meta status-${rowLife.tone}`}>
                  {rowLife.text} · {agentRowSubtitle(agent)}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="agent-detail-panel route-card">
        {detailLoading && (
          <div className="page-state loading compact">
            <div className="page-state-indicator" aria-hidden />
            <p>正在加载工作区详情…</p>
          </div>
        )}
        {!detailLoading && detailError && (
          <div className="page-state error compact">
            <div className="page-state-indicator" aria-hidden />
            <h3>加载失败</h3>
            <p>{detailError}</p>
            <button type="button" className="mgr-btn" onClick={() => void loadDetail(selectedAgentId)}>重试</button>
          </div>
        )}
        {!detailLoading && !detailError && selected && (
          <>
            <div className="agent-detail-head">
              <h2 className="agent-detail-id mono">{selected.agent_id}</h2>
              <p className={`agent-detail-status status-${lifecycle?.tone ?? 'idle'}`}>
                {(lifecycle?.text ?? '未知').toUpperCase()} · 最近活动 {formatRelativeTime(latestActivity)}
              </p>
            </div>

            <div className="agent-info-grid">
              <div className="agent-info-card">
                <span className="agent-info-label">模型</span>
                <span className="agent-info-value">{resolveModelLabel(selected, defaultModel)}</span>
              </div>
              <div className="agent-info-card">
                <span className="agent-info-label">Checkpoint</span>
                <span className="agent-info-value mono">{checkpointLabel(checkpointBackend)}</span>
              </div>
              <div className="agent-info-card">
                <span className="agent-info-label">技能</span>
                <span className="agent-info-value">
                  {enabledSkills !== null ? `${enabledSkills} 已启用` : `${selected.skills_count} 工作区技能`}
                </span>
              </div>
              <div className="agent-info-card">
                <span className="agent-info-label">工作区</span>
                <span className="agent-info-value mono agent-info-path" title={selected.root}>{selected.root}</span>
              </div>
            </div>

            <h3 className="agent-section-title">可用能力</h3>
            <div className="agent-capability-grid">
              {capabilities.map(cap => (
                <div key={cap.label} className={`agent-capability${cap.available ? '' : ' unavailable'}`}>
                  {cap.label}
                  {!cap.available && <span className="cap-unavailable">暂无数据</span>}
                </div>
              ))}
            </div>

            <div className="agent-action-row">
              <button
                type="button"
                className="mgr-btn primary-action"
                onClick={() => {
                  onSwitch(selected.agent_id)
                  onOpenChat(selected.agent_id)
                }}
              >
                打开工作区
              </button>
              {selected.agent_id !== currentAgent && (
                <button type="button" className="mgr-btn secondary" onClick={() => onSwitch(selected.agent_id)}>
                  设为当前
                </button>
              )}
              <button
                type="button"
                className="mgr-btn secondary"
                disabled={selected.agent_id === 'default'}
                onClick={() => void handleArchive()}
              >
                归档
              </button>
              <button
                type="button"
                className="mgr-btn danger"
                disabled={selected.agent_id === 'default'}
                onClick={() => void handlePurge()}
              >
                彻底清理
              </button>
            </div>
            {actionError && <div className="detail-action-error" role="alert">{actionError}</div>}

            <details className="agent-expand-section">
              <summary>工作区技能</summary>
              <SkillsManager agentId={selected.agent_id} />
            </details>

            <details className="agent-expand-section">
              <summary>运行历史与文件索引</summary>
              <div className="agent-index-grid">
                <div className="mgr-list">
                  <div className="mgr-section-title">运行历史</div>
                  {agentHistory.length === 0 && <div className="empty-hint">暂无该 Agent 的任务或会话历史。</div>}
                  {agentHistory.map(item => (
                    <div className="mgr-item" key={`${item.type}-${item.id}`}>
                      <div className="mgr-item-main">
                        <h4>{item.type} · {item.title}</h4>
                        <p>{item.status} · thread {item.thread_id || '—'} · trace {item.trace_id || '—'}</p>
                      </div>
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
            </details>
          </>
        )}
      </div>

      <aside className="agent-runtime-column" aria-label="运行状态">
        <div className="route-card agent-runtime-panel">
          <div className="route-card-header"><span>运行状态</span></div>
          {runtime.loading && <div className="empty-hint">加载中…</div>}
          {!runtime.loading && runtime.error && (
            <div className="detail-action-error">{runtime.error}</div>
          )}
          {!runtime.loading && !runtime.error && (
            <dl className="agent-runtime-stats">
              <div><dt>活动任务</dt><dd className="mono">{runtime.activeTasks}</dd></div>
              <div><dt>待审批</dt><dd className="mono">{runtime.pendingApprovals}</dd></div>
              <div><dt>Trace 事件</dt><dd className="mono">{runtime.traceEvents}</dd></div>
              <div><dt>最近错误</dt><dd className={`mono${runtime.recentErrors === 0 ? ' success' : ' warning'}`}>
                {runtime.recentErrors === 0 ? '无' : runtime.recentErrors}
              </dd></div>
            </dl>
          )}
        </div>
        <div className="route-card agent-boundary-panel">
          <div className="route-card-header"><span className="boundary-title">能力边界</span></div>
          <ul className="agent-boundary-list">
            <li>单机工作区隔离</li>
            <li>不支持多实例协调</li>
            <li>清理操作必须二次确认</li>
            <li>领域数据模块已从产品界面移除</li>
          </ul>
        </div>
      </aside>
    </div>
  )
}
