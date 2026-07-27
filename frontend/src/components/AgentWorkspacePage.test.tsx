import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentWorkspacePage from './AgentWorkspacePage'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    fetchAgents: vi.fn(),
    fetchAgent: vi.fn(),
    fetchAgentProfile: vi.fn(),
    fetchAgentProfileVersions: vi.fn(),
    fetchAgentFiles: vi.fn(),
    fetchAgentHistory: vi.fn(),
    fetchSkills: vi.fn(),
    fetchProviders: vi.fn(),
    fetchProviderModels: vi.fn(),
    fetchDefaultProviderConfig: vi.fn(),
    fetchMonitorHealth: vi.fn(),
    fetchStats: vi.fn(),
    fetchTasks: vi.fn(),
    fetchApprovals: vi.fn(),
    createAgentWithProfile: vi.fn(),
    deleteAgent: vi.fn(),
  }
})

vi.mock('./SkillsManager', () => ({
  default: () => <div data-testid="skills-manager-stub" />,
}))

import {
  fetchAgent,
  fetchAgentFiles,
  fetchAgentHistory,
  fetchAgentProfile,
  fetchAgentProfileVersions,
  fetchAgents,
  fetchApprovals,
  fetchDefaultProviderConfig,
  fetchMonitorHealth,
  fetchProviderModels,
  fetchProviders,
  fetchSkills,
  fetchStats,
  fetchTasks,
} from '../services/api'

const mockedFetchAgents = vi.mocked(fetchAgents)
const mockedFetchAgent = vi.mocked(fetchAgent)
const mockedFetchAgentProfile = vi.mocked(fetchAgentProfile)
const mockedFetchAgentProfileVersions = vi.mocked(fetchAgentProfileVersions)
const mockedFetchAgentFiles = vi.mocked(fetchAgentFiles)
const mockedFetchAgentHistory = vi.mocked(fetchAgentHistory)
const mockedFetchSkills = vi.mocked(fetchSkills)
const mockedFetchProviders = vi.mocked(fetchProviders)
const mockedFetchProviderModels = vi.mocked(fetchProviderModels)
const mockedFetchDefaultProviderConfig = vi.mocked(fetchDefaultProviderConfig)
const mockedFetchMonitorHealth = vi.mocked(fetchMonitorHealth)
const mockedFetchStats = vi.mocked(fetchStats)
const mockedFetchTasks = vi.mocked(fetchTasks)
const mockedFetchApprovals = vi.mocked(fetchApprovals)

const profileFixture = {
  agent_id: 'default',
  configured: {
    display_name: '默认智能体',
    description: '',
    avatar_color: '#6366f1',
    system_prompt: '',
    provider: 'openai',
    model: 'gpt-5',
    temperature: null,
    max_output_tokens: null,
    tool_policy: 'inherit' as const,
    tool_allowlist: [] as string[],
    memory_mode: 'inherit' as const,
    default_language: 'zh',
    enabled: true,
  },
  effective: {
    display_name: '默认智能体',
    description: '',
    avatar_color: '#6366f1',
    system_prompt: '',
    provider: 'openai',
    model: 'gpt-5',
    model_string: 'openai:gpt-5',
    temperature: null,
    max_output_tokens: null,
    tool_policy: 'inherit' as const,
    tool_allowlist: [] as string[],
    memory_mode: 'inherit' as const,
    default_language: 'zh',
    enabled: true,
    revision: 1,
  },
  revision: 1,
  apply_state: { revision: 1, status: 'applied' as const, applied_at: '2026-07-16T00:00:00Z', error_summary: '' },
}

function setupMocks() {
  mockedFetchAgents.mockResolvedValue({
    agents: [
      {
        agent_id: 'default',
        root: '/workspace/agents/default',
        created_at: '2026-07-16T00:00:00Z',
        loaded: true,
        skills_count: 2,
        config: { model: 'gpt-5', provider: 'openai' },
        profile: { display_name: '默认智能体', enabled: true, revision: 1 },
      },
      {
        agent_id: 'analysis-agent',
        root: '/workspace/agents/analysis-agent',
        created_at: '2026-07-16T00:00:00Z',
        loaded: false,
        skills_count: 0,
        config: {},
      },
    ],
  })
  mockedFetchAgent.mockResolvedValue({
    agent_id: 'default',
    root: '/workspace/agents/default',
    created_at: '2026-07-16T00:00:00Z',
    loaded: true,
    skills_count: 2,
    config: { model: 'gpt-5', provider: 'openai' },
  })
  mockedFetchAgentProfile.mockResolvedValue(profileFixture)
  mockedFetchAgentProfileVersions.mockResolvedValue({ agent_id: 'default', total: 1, offset: 0, limit: 20, versions: [{ revision: 1, created_at: '2026-07-16T00:00:00Z', changed_fields: ['created'], operator: 'system' }] })
  mockedFetchAgentFiles.mockResolvedValue({ agent_id: 'default', root: '/workspace/agents/default/files', files: [] })
  mockedFetchAgentHistory.mockResolvedValue({ agent_id: 'default', history: [] })
  mockedFetchSkills.mockResolvedValue({ pool: [], workspace: [{ name: 'demo', description: '', path: '', source: '', enabled: true, languages: [], metadata: {} }] })
  mockedFetchProviders.mockResolvedValue({ providers: [{ name: 'openai', display_name: 'OpenAI', configured: true, default_model: 'gpt-5', requires_api_key: true }] })
  mockedFetchProviderModels.mockResolvedValue({ models: [{ name: 'gpt-5', provider: 'openai', context_window: 128000, supports_tools: true, supports_vision: true }] })
  mockedFetchDefaultProviderConfig.mockResolvedValue({ provider: 'openai', model: 'gpt-5' })
  mockedFetchMonitorHealth.mockResolvedValue({
    status: 'healthy',
    ready: true,
    agent_ready: true,
    checkpoint: {
      status: 'ready',
      backend: 'sqlite',
      persistent: true,
      supports_restart_resume: true,
      warning: '',
      sqlite_path: '/data/checkpoints',
      open_agent_savers: 1,
      error: '',
    },
  })
  mockedFetchStats.mockResolvedValue({ tasks: {}, trace_events: 248, event_types: {} })
  mockedFetchTasks.mockResolvedValue([])
  mockedFetchApprovals.mockResolvedValue({ pending: [{} as never] })
}

beforeEach(() => {
  vi.clearAllMocks()
  setupMocks()
})

describe('AgentWorkspacePage', () => {
  it('展示 Agent 列表与配置工作室标签', async () => {
    render(
      <AgentWorkspacePage
        currentAgent="default"
        selectedAgentId="default"
        onSwitch={vi.fn()}
        onSelect={vi.fn()}
        onDeleted={vi.fn()}
        onOpenChat={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getAllByText('default').length).toBeGreaterThan(0))
    expect(screen.getByText('analysis-agent')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('tab', { name: '配置' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '默认智能体' })).toBeInTheDocument()
    expect(screen.getByText('248')).toBeInTheDocument()
  })

  it('支持 Agent 搜索过滤', async () => {
    const user = userEvent.setup()
    render(
      <AgentWorkspacePage
        currentAgent="default"
        selectedAgentId="default"
        onSwitch={vi.fn()}
        onSelect={vi.fn()}
        onDeleted={vi.fn()}
        onOpenChat={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByText('analysis-agent')).toBeInTheDocument())
    await user.type(screen.getByPlaceholderText('搜索 Agent…'), 'analysis')
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByText('analysis-agent')).toBeInTheDocument()
  })

  it('列表加载失败时显示错误状态', async () => {
    mockedFetchAgents.mockRejectedValueOnce(new Error('agents unavailable'))

    render(
      <AgentWorkspacePage
        currentAgent="default"
        selectedAgentId="default"
        onSwitch={vi.fn()}
        onSelect={vi.fn()}
        onDeleted={vi.fn()}
        onOpenChat={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByText('agents unavailable')).toBeInTheDocument())
  })

  it('详情加载失败后可重试成功', async () => {
    mockedFetchAgent
      .mockRejectedValueOnce(new Error('detail unavailable'))
      .mockResolvedValue({
        agent_id: 'default',
        root: '/workspace/agents/default',
        created_at: '2026-07-16T00:00:00Z',
        loaded: true,
        skills_count: 2,
        config: { model: 'gpt-5', provider: 'openai' },
      })

    const user = userEvent.setup()
    render(
      <AgentWorkspacePage
        currentAgent="default"
        selectedAgentId="default"
        onSwitch={vi.fn()}
        onSelect={vi.fn()}
        onDeleted={vi.fn()}
        onOpenChat={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByText('detail unavailable')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '加载失败' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '默认智能体' })).toBeInTheDocument())
    expect(mockedFetchAgent).toHaveBeenCalledTimes(2)
    expect(mockedFetchAgent).toHaveBeenLastCalledWith('default')
  })
})
