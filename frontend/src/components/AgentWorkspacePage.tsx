import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  cloneAgent,
  createAgentWithProfile,
  deleteAgent,
  exportAgentProfile,
  fetchAgent,
  fetchAgentFiles,
  fetchAgentHistory,
  fetchAgentProfile,
  fetchAgentProfileVersionDetail,
  fetchAgentProfileVersions,
  fetchAgents,
  fetchApprovals,
  fetchDefaultProviderConfig,
  fetchMonitorHealth,
  fetchConnectionModels,
  fetchProviderConnections,
  fetchProviderModels,
  fetchProviders,
  fetchSkills,
  fetchStats,
  fetchTasks,
  importAgentProfile,
  rollbackAgentProfile,
  updateAgentProfile,
  validateAgentProfile,
  type AgentFileInfo,
  type AgentHistoryItem,
  type AgentInfo,
  type AgentProfileConfigured,
  type AgentProfileResponse,
  type AgentProfileVersionSummary,
  type ModelInfo,
  type ProviderConnectionInfo,
  type ProviderInfo,
} from '../services/api'
import { capabilityTags } from '../utils/modelCapabilities'
import SkillsManager from './SkillsManager'
import AgentKnowledgeBindings from './AgentKnowledgeBindings'
import ResourceAccessPanel from './ResourceAccessPanel'

interface AgentWorkspacePageProps {
  currentAgent: string
  selectedAgentId: string
  createTrigger?: number
  onSwitch: (agentId: string) => void
  onSelect: (agentId: string) => void
  onDeleted: (agentId: string) => void
  onOpenChat: (agentId: string) => void
}

type WorkspaceTab = 'overview' | 'config' | 'skills' | 'knowledge' | 'files' | 'history' | 'versions' | 'access'
type WizardStep = 'identity' | 'model' | 'behavior' | 'capabilities' | 'confirm'

const TABS: Array<{ id: WorkspaceTab; label: string }> = [
  { id: 'overview', label: '概览' },
  { id: 'config', label: '配置' },
  { id: 'skills', label: '技能' },
  { id: 'knowledge', label: '知识库' },
  { id: 'access', label: '访问权限' },
  { id: 'files', label: '文件' },
  { id: 'history', label: '历史' },
  { id: 'versions', label: '版本' },
]

const WIZARD_STEPS: Array<{ id: WizardStep; label: string }> = [
  { id: 'identity', label: '身份' },
  { id: 'model', label: '模型' },
  { id: 'behavior', label: '行为' },
  { id: 'capabilities', label: '能力' },
  { id: 'confirm', label: '确认' },
]

const EMPTY_PROFILE: AgentProfileConfigured = {
  display_name: '',
  description: '',
  avatar_color: '#6366f1',
  system_prompt: '',
  provider: '',
  model: '',
  temperature: null,
  max_output_tokens: null,
  tool_policy: 'inherit',
  tool_allowlist: [],
  memory_mode: 'inherit',
  default_language: 'zh',
  enabled: true,
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
  const profileName = agent.profile?.display_name
  if (profileName) return profileName
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

function resolveModelLabel(profile: AgentProfileResponse | null, defaultModel: string | null): string {
  if (!profile) return defaultModel ?? '未配置（使用全局默认）'
  const configured = profile.configured
  if (configured.model && configured.provider) return `${configured.provider}/${configured.model}`
  if (configured.model) return configured.model
  const effective = profile.effective
  if (effective.provider && effective.model) return `${effective.provider}/${effective.model}（继承）`
  return defaultModel ?? '未配置（使用全局默认）'
}

function checkpointLabel(backend: string | undefined): string {
  if (!backend) return '不可用'
  if (backend === 'sqlite') return 'SQLite'
  if (backend === 'memory') return 'Memory（不持久）'
  return backend
}

function profilesEqual(a: AgentProfileConfigured, b: AgentProfileConfigured): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
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
  const [profile, setProfile] = useState<AgentProfileResponse | null>(null)
  const [draft, setDraft] = useState<AgentProfileConfigured>(EMPTY_PROFILE)
  const [agentFiles, setAgentFiles] = useState<AgentFileInfo[]>([])
  const [agentHistory, setAgentHistory] = useState<AgentHistoryItem[]>([])
  const [versions, setVersions] = useState<AgentProfileVersionSummary[]>([])
  const [versionDetailRevision, setVersionDetailRevision] = useState<number | null>(null)
  const [versionDetail, setVersionDetail] = useState<string[]>([])
  const [enabledSkills, setEnabledSkills] = useState<number | null>(null)
  const [defaultModel, setDefaultModel] = useState<string | null>(null)
  const [checkpointBackend, setCheckpointBackend] = useState<string | undefined>()
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [connections, setConnections] = useState<ProviderConnectionInfo[]>([])
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelInfo[]>>({})
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview')
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
  const [actionInfo, setActionInfo] = useState('')
  const [creating, setCreating] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [wizardStep, setWizardStep] = useState<WizardStep>('identity')
  const [wizardProfile, setWizardProfile] = useState<AgentProfileConfigured & { agent_id: string }>({
    ...EMPTY_PROFILE,
    agent_id: '',
  })
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validationMessages, setValidationMessages] = useState<string[]>([])

  const dirty = useMemo(
    () => profile ? !profilesEqual(draft, profile.configured) : false,
    [draft, profile],
  )

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
      setRuntime({
        activeTasks: tasks.filter(t => t.status === 'running' || t.status === 'pending').length,
        pendingApprovals: approvals.pending.length,
        traceEvents: stats.trace_events,
        recentErrors: tasks.filter(t => t.status === 'failed').length,
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

  const loadProviders = useCallback(async () => {
    try {
      const [providerResp, connResp] = await Promise.all([
        fetchProviders(),
        fetchProviderConnections(true),
      ])
      const configured = providerResp.providers.filter(p => p.configured)
      setProviders(configured)
      setConnections(connResp.connections)
      const modelMap: Record<string, ModelInfo[]> = {}
      await Promise.all(
        connResp.connections.map(async conn => {
          try {
            const resp = await fetchConnectionModels(conn.id)
            modelMap[conn.id] = resp.models
          } catch {
            modelMap[conn.id] = []
          }
        }),
      )
      await Promise.all(
        configured.map(async provider => {
          if (modelMap[provider.name]) return
          try {
            const resp = await fetchProviderModels(provider.name)
            modelMap[provider.name] = resp.models
          } catch {
            modelMap[provider.name] = []
          }
        }),
      )
      setModelsByProvider(modelMap)
    } catch {
      setProviders([])
      setConnections([])
      setModelsByProvider({})
    }
  }, [])

  useEffect(() => {
    void loadAgents()
    void loadRuntime()
    void loadProviders()
    fetchDefaultProviderConfig()
      .then(cfg => setDefaultModel(cfg.model ? `${cfg.provider}/${cfg.model}` : cfg.provider || null))
      .catch(() => setDefaultModel(null))
    fetchMonitorHealth()
      .then(health => setCheckpointBackend(health.checkpoint?.backend))
      .catch(() => setCheckpointBackend(undefined))
  }, [loadProviders])

  useEffect(() => {
    if (createTrigger > 0) setShowWizard(true)
  }, [createTrigger])

  const switchTab = (tab: WorkspaceTab) => {
    if (dirty && tab !== activeTab) {
      if (!window.confirm('配置有未保存修改，确定离开当前页？')) return
    }
    setActiveTab(tab)
  }

  const loadDetail = async (agentId: string) => {
    setDetailLoading(true)
    setDetailError('')
    setActionError('')
    setActionInfo('')
    setEnabledSkills(null)
    setVersionDetailRevision(null)
    setVersionDetail([])
    try {
      const [detail, profileResp, files, history, skills, versionResp] = await Promise.all([
        fetchAgent(agentId),
        fetchAgentProfile(agentId),
        fetchAgentFiles(agentId),
        fetchAgentHistory(agentId),
        fetchSkills(agentId).catch(() => ({ pool: [], workspace: [] })),
        fetchAgentProfileVersions(agentId).catch(() => ({ agent_id: agentId, total: 0, offset: 0, limit: 20, versions: [] })),
      ])
      setSelected(detail)
      setProfile(profileResp)
      setDraft(profileResp.configured)
      setAgentFiles(files.files)
      setAgentHistory(history.history)
      setVersions(versionResp.versions)
      setEnabledSkills(skills.workspace.filter(s => s.enabled).length)
    } catch (e) {
      setSelected(null)
      setProfile(null)
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

  const handleValidate = async () => {
    if (!profile) return
    setValidating(true)
    setValidationMessages([])
    setActionError('')
    try {
      const result = await validateAgentProfile(selectedAgentId, draft, profile.revision)
      setValidationMessages([...result.errors, ...result.warnings])
      if (result.valid) setActionInfo('验证通过，可保存配置')
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setValidating(false)
    }
  }

  const handleSaveProfile = async () => {
    if (!profile) return
    setSaving(true)
    setActionError('')
    setActionInfo('')
    try {
      const updated = await updateAgentProfile(selectedAgentId, profile.revision, draft)
      setProfile(updated)
      setDraft(updated.configured)
      setActionInfo('配置已保存并应用')
      await loadAgents()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleVersionPreview = async (revision: number) => {
    setActionError('')
    try {
      const detail = await fetchAgentProfileVersionDetail(selectedAgentId, revision)
      setVersionDetailRevision(revision)
      setVersionDetail(detail.diff_from_current)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleRollback = async (revision: number) => {
    if (!window.confirm(`确认回滚到 revision ${revision}？此操作会生成新的 revision。`)) return
    setActionError('')
    try {
      const updated = await rollbackAgentProfile(selectedAgentId, revision)
      setProfile(updated)
      setDraft(updated.configured)
      setActionInfo(`已回滚到 revision ${revision}`)
      const versionResp = await fetchAgentProfileVersions(selectedAgentId)
      setVersions(versionResp.versions)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleClone = async () => {
    if (!selected) return
    setActionError('')
    try {
      const cloned = await cloneAgent(selected.agent_id)
      await loadAgents()
      onSelect(cloned.agent_id)
      setActionInfo(`已复制为 ${cloned.agent_id}（不含会话、记忆、文件与 trace）`)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleExport = async () => {
    if (!selected) return
    setActionError('')
    try {
      const payload = await exportAgentProfile(selected.agent_id)
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${selected.agent_id}-profile.json`
      anchor.click()
      URL.revokeObjectURL(url)
      setActionInfo('配置已导出（不含密钥与运行历史）')
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleImportFile = async (file: File) => {
    setActionError('')
    try {
      const text = await file.text()
      const payload = JSON.parse(text) as Record<string, unknown>
      const imported = await importAgentProfile(payload)
      await loadAgents()
      onSelect(imported.agent_id)
      setActionInfo(`已导入 Agent ${imported.agent_id}`)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleWizardCreate = async () => {
    const id = wizardProfile.agent_id.trim()
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
      const { agent_id: _ignored, ...profilePayload } = wizardProfile
      await createAgentWithProfile(id, profilePayload)
      setShowWizard(false)
      setWizardStep('identity')
      setWizardProfile({ ...EMPTY_PROFILE, agent_id: '' })
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

  const renderOverview = () => (
    <>
      <div className="agent-info-grid">
        <div className="agent-info-card">
          <span className="agent-info-label">显示名称</span>
          <span className="agent-info-value">{profile?.configured.display_name || selected?.agent_id}</span>
        </div>
        <div className="agent-info-card">
          <span className="agent-info-label">模型</span>
          <span className="agent-info-value">{resolveModelLabel(profile, defaultModel)}</span>
        </div>
        <div className="agent-info-card">
          <span className="agent-info-label">Revision</span>
          <span className="agent-info-value mono">{profile?.revision ?? '—'}</span>
        </div>
        <div className="agent-info-card">
          <span className="agent-info-label">Checkpoint</span>
          <span className="agent-info-value mono">{checkpointLabel(checkpointBackend)}</span>
        </div>
        <div className="agent-info-card">
          <span className="agent-info-label">技能</span>
          <span className="agent-info-value">
            {enabledSkills !== null ? `${enabledSkills} 已启用` : `${selected?.skills_count ?? 0} 工作区技能`}
          </span>
        </div>
        <div className="agent-info-card">
          <span className="agent-info-label">应用状态</span>
          <span className="agent-info-value">{profile?.apply_state.status ?? '—'}</span>
        </div>
      </div>
      <div className="agent-action-row">
        <button type="button" className="mgr-btn primary-action" onClick={() => { onSwitch(selected!.agent_id); onOpenChat(selected!.agent_id) }}>
          打开工作区
        </button>
        {selected!.agent_id !== currentAgent && (
          <button type="button" className="mgr-btn secondary" onClick={() => onSwitch(selected!.agent_id)}>设为当前</button>
        )}
        <button type="button" className="mgr-btn secondary" onClick={() => void handleClone()}>复制</button>
        <button type="button" className="mgr-btn secondary" onClick={() => void handleExport()}>导出</button>
        <label className="mgr-btn secondary agent-import-btn">
          导入
          <input type="file" accept="application/json" hidden onChange={e => { const f = e.target.files?.[0]; if (f) void handleImportFile(f); e.target.value = '' }} />
        </label>
        <button type="button" className="mgr-btn secondary" disabled={selected!.agent_id === 'default'} onClick={() => void handleArchive()}>归档</button>
        <button type="button" className="mgr-btn danger" disabled={selected!.agent_id === 'default'} onClick={() => void handlePurge()}>彻底清理</button>
      </div>
      <p className="agent-boundary-note">复制/导入仅携带配置与可选技能引用，不包含会话、记忆、Checkpoint、文件、任务或 trace。</p>
    </>
  )

  const renderConfig = () => (
    <div className="agent-config-form mgr-form">
      <div className="agent-config-grid">
        <label>
          显示名称
          <input value={draft.display_name} onChange={e => setDraft(v => ({ ...v, display_name: e.target.value }))} />
        </label>
        <label>
          头像色
          <input type="color" value={draft.avatar_color} onChange={e => setDraft(v => ({ ...v, avatar_color: e.target.value }))} />
        </label>
        <label className="full-width">
          描述
          <textarea value={draft.description} rows={2} onChange={e => setDraft(v => ({ ...v, description: e.target.value }))} />
        </label>
        <label className="full-width">
          职责提示词
          <textarea
            value={draft.system_prompt}
            rows={6}
            onChange={e => setDraft(v => ({ ...v, system_prompt: e.target.value }))}
            aria-describedby="prompt-help"
          />
          <span id="prompt-help" className="field-hint">
            {draft.system_prompt.length} 字符 · 提示词受平台 ToolGuard 约束，不能替代系统安全策略
          </span>
        </label>
        <label>
          模型连接（留空继承）
          <select value={draft.provider} onChange={e => setDraft(v => ({ ...v, provider: e.target.value, model: '' }))}>
            <option value="">继承全局</option>
            {connections.map(c => (
              <option key={c.id} value={c.id}>{c.display_name} ({c.provider_type})</option>
            ))}
            {connections.length === 0 && providers.map(p => (
              <option key={p.name} value={p.name}>{p.display_name || p.name}</option>
            ))}
          </select>
        </label>
        <label>
          模型（留空继承）
          <select
            value={draft.model}
            disabled={!draft.provider}
            onChange={e => setDraft(v => ({ ...v, model: e.target.value }))}
          >
            <option value="">{draft.provider ? '选择模型' : '继承全局'}</option>
            {(modelsByProvider[draft.provider] ?? []).map(model => (
              <option key={model.name} value={model.name}>
                {model.name} · {capabilityTags(model).join(' ')}
              </option>
            ))}
          </select>
        </label>
        <label>
          有效模型
          <input readOnly className="readonly" value={resolveModelLabel(profile, defaultModel)} />
        </label>
        <label>
          温度
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={draft.temperature ?? ''}
            onChange={e => setDraft(v => ({ ...v, temperature: e.target.value ? Number(e.target.value) : null }))}
          />
        </label>
        <label>
          最大输出 Token
          <input
            type="number"
            min="1"
            value={draft.max_output_tokens ?? ''}
            onChange={e => setDraft(v => ({ ...v, max_output_tokens: e.target.value ? Number(e.target.value) : null }))}
          />
        </label>
        <label>
          工具策略
          <select value={draft.tool_policy} onChange={e => setDraft(v => ({ ...v, tool_policy: e.target.value as AgentProfileConfigured['tool_policy'] }))}>
            <option value="inherit">继承平台默认</option>
            <option value="safe_only">仅安全工具</option>
            <option value="allowlist">指定允许列表</option>
          </select>
        </label>
        <label>
          记忆模式
          <select value={draft.memory_mode} onChange={e => setDraft(v => ({ ...v, memory_mode: e.target.value as AgentProfileConfigured['memory_mode'] }))}>
            <option value="inherit">继承</option>
            <option value="off">关闭</option>
            <option value="review">审核</option>
            <option value="auto">自动</option>
          </select>
        </label>
        <label className="full-width">
          工具允许列表（逗号分隔）
          <input
            value={draft.tool_allowlist.join(', ')}
            disabled={draft.tool_policy !== 'allowlist'}
            onChange={e => setDraft(v => ({ ...v, tool_allowlist: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={draft.enabled}
            disabled={selected?.agent_id === 'default'}
            onChange={e => setDraft(v => ({ ...v, enabled: e.target.checked }))}
          />
          启用 Agent
        </label>
      </div>
      {validationMessages.length > 0 && (
        <ul className="validation-list" role="status">
          {validationMessages.map(msg => <li key={msg}>{msg}</li>)}
        </ul>
      )}
      <div className="agent-action-row">
        <button type="button" className="mgr-btn secondary" disabled={validating} onClick={() => void handleValidate()}>
          {validating ? '验证中…' : '验证配置'}
        </button>
        <button type="button" className="mgr-btn primary-action" disabled={saving || !dirty} onClick={() => void handleSaveProfile()}>
          {saving ? '保存中…' : dirty ? '保存并应用' : '已保存'}
        </button>
      </div>
    </div>
  )

  const renderVersions = () => (
    <div className="agent-versions-panel">
      <p className="field-hint">回滚会生成新的 revision，不会删除历史版本。</p>
      <div className="mgr-list">
        {versions.length === 0 && <div className="empty-hint">暂无版本记录。</div>}
        {versions.map(item => (
          <div className="mgr-item" key={item.revision}>
            <div className="mgr-item-main">
              <h4>revision {item.revision}</h4>
              <p>{new Date(item.created_at).toLocaleString('zh-CN')} · {item.changed_fields.join(', ') || '初始'}</p>
            </div>
            <div className="mgr-item-actions">
              <button type="button" className="mgr-btn secondary compact" onClick={() => void handleVersionPreview(item.revision)}>差异</button>
              <button type="button" className="mgr-btn secondary compact" onClick={() => void handleRollback(item.revision)}>回滚</button>
            </div>
          </div>
        ))}
      </div>
      {versionDetailRevision !== null && (
        <div className="agent-version-diff">
          <div className="mgr-section-title">与当前差异（revision {versionDetailRevision}）</div>
          {versionDetail.length === 0
            ? <div className="empty-hint">与当前配置一致</div>
            : <ul>{versionDetail.map(field => <li key={field} className="mono">{field}</li>)}</ul>}
        </div>
      )}
    </div>
  )

  const renderWizard = () => {
    if (!showWizard) return null
    const stepIndex = WIZARD_STEPS.findIndex(s => s.id === wizardStep)
    return (
      <div className="agent-wizard-overlay" role="dialog" aria-modal="true" aria-label="创建 Agent">
        <div className="agent-wizard route-card">
          <div className="route-card-header"><span>创建 Agent</span></div>
          <div className="agent-wizard-steps">
            {WIZARD_STEPS.map((step, index) => (
              <span key={step.id} className={`wizard-step${index <= stepIndex ? ' active' : ''}`}>{step.label}</span>
            ))}
          </div>
          {wizardStep === 'identity' && (
            <div className="mgr-form">
              <label>Agent ID<input value={wizardProfile.agent_id} onChange={e => setWizardProfile(v => ({ ...v, agent_id: e.target.value, display_name: v.display_name || e.target.value }))} autoFocus /></label>
              <label>显示名称<input value={wizardProfile.display_name} onChange={e => setWizardProfile(v => ({ ...v, display_name: e.target.value }))} /></label>
              <label>描述<textarea rows={2} value={wizardProfile.description} onChange={e => setWizardProfile(v => ({ ...v, description: e.target.value }))} /></label>
            </div>
          )}
          {wizardStep === 'model' && (
            <div className="mgr-form">
              <label>模型连接（可留空）<select value={wizardProfile.provider} onChange={e => setWizardProfile(v => ({ ...v, provider: e.target.value, model: '' }))}><option value="">继承</option>{connections.map(c => <option key={c.id} value={c.id}>{c.display_name}</option>)}{connections.length === 0 && providers.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}</select></label>
              <label>模型<select value={wizardProfile.model} disabled={!wizardProfile.provider} onChange={e => setWizardProfile(v => ({ ...v, model: e.target.value }))}><option value="">继承</option>{(modelsByProvider[wizardProfile.provider] ?? []).map(m => <option key={m.name} value={m.name}>{m.name}</option>)}</select></label>
            </div>
          )}
          {wizardStep === 'behavior' && (
            <div className="mgr-form">
              <label className="full-width">职责提示词<textarea rows={5} value={wizardProfile.system_prompt} onChange={e => setWizardProfile(v => ({ ...v, system_prompt: e.target.value }))} /></label>
              <label>工具策略<select value={wizardProfile.tool_policy} onChange={e => setWizardProfile(v => ({ ...v, tool_policy: e.target.value as AgentProfileConfigured['tool_policy'] }))}><option value="inherit">继承</option><option value="safe_only">仅安全工具</option><option value="allowlist">允许列表</option></select></label>
            </div>
          )}
          {wizardStep === 'capabilities' && (
            <div className="mgr-form">
              <label>记忆模式<select value={wizardProfile.memory_mode} onChange={e => setWizardProfile(v => ({ ...v, memory_mode: e.target.value as AgentProfileConfigured['memory_mode'] }))}><option value="inherit">继承</option><option value="review">审核</option><option value="auto">自动</option><option value="off">关闭</option></select></label>
              <p className="field-hint">平台 ToolGuard 始终开启，无法通过配置关闭。</p>
            </div>
          )}
          {wizardStep === 'confirm' && (
            <div className="agent-wizard-summary">
              <p><strong>ID：</strong>{wizardProfile.agent_id || '—'}</p>
              <p><strong>名称：</strong>{wizardProfile.display_name || wizardProfile.agent_id || '—'}</p>
              <p><strong>模型：</strong>{wizardProfile.provider && wizardProfile.model ? `${wizardProfile.provider}/${wizardProfile.model}` : '继承全局默认'}</p>
              <p className="field-hint">仅创建配置与工作区目录，不含历史数据。</p>
            </div>
          )}
          <div className="agent-action-row">
            <button type="button" className="mgr-btn secondary" onClick={() => setShowWizard(false)}>取消</button>
            {stepIndex > 0 && <button type="button" className="mgr-btn secondary" onClick={() => setWizardStep(WIZARD_STEPS[stepIndex - 1].id)}>上一步</button>}
            {stepIndex < WIZARD_STEPS.length - 1
              ? <button type="button" className="mgr-btn" onClick={() => setWizardStep(WIZARD_STEPS[stepIndex + 1].id)}>下一步</button>
              : <button type="button" className="mgr-btn primary-action" disabled={creating} onClick={() => void handleWizardCreate()}>{creating ? '创建中…' : '创建 Agent'}</button>}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="agent-workspace-page">
      {renderWizard()}
      <div className="agent-list-panel route-card">
        <div className="route-card-header agent-list-header">
          <span>Agent</span>
          <button type="button" className="mgr-btn secondary compact" onClick={() => setShowWizard(true)}>新建</button>
          <button type="button" className="mgr-btn secondary compact" onClick={() => void loadAgents()} disabled={listLoading}>
            {listLoading ? '…' : '刷新'}
          </button>
        </div>
        <div className="agent-search">
          <input type="search" placeholder="搜索 Agent…" value={query} onChange={e => setQuery(e.target.value)} aria-label="搜索 Agent" />
        </div>
        {listError && <div className="detail-action-error" role="alert">{listError}</div>}
        <div className="agent-list" role="listbox" aria-label="Agent 列表">
          {listLoading && agents.length === 0 && <div className="page-state loading compact"><p>正在加载 Agent…</p></div>}
          {!listLoading && filteredAgents.length === 0 && <div className="page-state empty compact"><p>{query ? '没有匹配的 Agent。' : '暂无 Agent 工作区。'}</p></div>}
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
                <span className={`agent-list-meta status-${rowLife.tone}`}>{rowLife.text} · {agentRowSubtitle(agent)}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="agent-detail-panel route-card">
        {detailLoading && <div className="page-state loading compact"><p>正在加载工作区详情…</p></div>}
        {!detailLoading && detailError && (
          <div className="page-state error compact">
            <h3>加载失败</h3>
            <p>{detailError}</p>
            <button type="button" className="mgr-btn" onClick={() => void loadDetail(selectedAgentId)}>重试</button>
          </div>
        )}
        {!detailLoading && !detailError && selected && (
          <>
            <div className="agent-detail-head">
              <h2 className="agent-detail-id">{profile?.configured.display_name || selected.agent_id}</h2>
              <p className="agent-detail-subtitle mono">{selected.agent_id}</p>
              <p className={`agent-detail-status status-${lifecycle?.tone ?? 'idle'}`}>
                {(lifecycle?.text ?? '未知').toUpperCase()} · 最近活动 {formatRelativeTime(latestActivity)}
              </p>
            </div>
            <div className="agent-tab-bar" role="tablist">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  className={`agent-tab${activeTab === tab.id ? ' active' : ''}${dirty && tab.id !== 'config' && activeTab === 'config' ? ' warn' : ''}`}
                  onClick={() => switchTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="agent-tab-panel" role="tabpanel">
              {activeTab === 'overview' && renderOverview()}
              {activeTab === 'config' && renderConfig()}
              {activeTab === 'skills' && <SkillsManager agentId={selected.agent_id} />}
              {activeTab === 'knowledge' && <AgentKnowledgeBindings agentId={selected.agent_id} />}
              {activeTab === 'access' && (
                <ResourceAccessPanel
                  resourceType="agent"
                  resourceId={selected.agent_id}
                  currentUser={{ role: 'owner', permissions: ['agents:admin'], open_mode: true }}
                />
              )}
              {activeTab === 'files' && (
                <div className="mgr-list">
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
              )}
              {activeTab === 'history' && (
                <div className="mgr-list">
                  {agentHistory.length === 0 && <div className="empty-hint">暂无该 Agent 的任务或会话历史。</div>}
                  {agentHistory.map(item => (
                    <div className="mgr-item" key={`${item.type}-${item.id}`}>
                      <div className="mgr-item-main">
                        <h4>{item.type} · {item.title}</h4>
                        <p>{item.status} · thread {item.thread_id || '—'}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {activeTab === 'versions' && renderVersions()}
            </div>
            {actionInfo && <div className="detail-action-info" role="status">{actionInfo}</div>}
            {actionError && <div className="detail-action-error" role="alert">{actionError}</div>}
          </>
        )}
      </div>

      <aside className="agent-runtime-column" aria-label="运行状态">
        <div className="route-card agent-runtime-panel">
          <div className="route-card-header"><span>运行状态</span></div>
          {!runtime.loading && !runtime.error && (
            <dl className="agent-runtime-stats">
              <div><dt>活动任务</dt><dd className="mono">{runtime.activeTasks}</dd></div>
              <div><dt>待审批</dt><dd className="mono">{runtime.pendingApprovals}</dd></div>
              <div><dt>Trace 事件</dt><dd className="mono">{runtime.traceEvents}</dd></div>
              <div><dt>最近错误</dt><dd className={`mono${runtime.recentErrors === 0 ? ' success' : ' warning'}`}>{runtime.recentErrors === 0 ? '无' : runtime.recentErrors}</dd></div>
            </dl>
          )}
        </div>
        <div className="route-card agent-boundary-panel">
          <div className="route-card-header"><span className="boundary-title">能力边界</span></div>
          <ul className="agent-boundary-list">
            <li>ToolGuard 不可关闭</li>
            <li>复制不含业务数据</li>
            <li>配置支持 revision 乐观并发</li>
          </ul>
        </div>
      </aside>
    </div>
  )
}
