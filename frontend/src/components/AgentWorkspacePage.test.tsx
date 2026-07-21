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
    fetchAgentFiles: vi.fn(),
    fetchAgentHistory: vi.fn(),
    fetchSkills: vi.fn(),
    fetchDefaultProviderConfig: vi.fn(),
    fetchMonitorHealth: vi.fn(),
    fetchStats: vi.fn(),
    fetchTasks: vi.fn(),
    fetchApprovals: vi.fn(),
    createAgent: vi.fn(),
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
  fetchAgents,
  fetchApprovals,
  fetchDefaultProviderConfig,
  fetchMonitorHealth,
  fetchSkills,
  fetchStats,
  fetchTasks,
} from '../services/api'

const mockedFetchAgents = vi.mocked(fetchAgents)
const mockedFetchAgent = vi.mocked(fetchAgent)
const mockedFetchAgentFiles = vi.mocked(fetchAgentFiles)
const mockedFetchAgentHistory = vi.mocked(fetchAgentHistory)
const mockedFetchSkills = vi.mocked(fetchSkills)
const mockedFetchDefaultProviderConfig = vi.mocked(fetchDefaultProviderConfig)
const mockedFetchMonitorHealth = vi.mocked(fetchMonitorHealth)
const mockedFetchStats = vi.mocked(fetchStats)
const mockedFetchTasks = vi.mocked(fetchTasks)
const mockedFetchApprovals = vi.mocked(fetchApprovals)

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
  mockedFetchAgentFiles.mockResolvedValue({ agent_id: 'default', root: '/workspace/agents/default/files', files: [] })
  mockedFetchAgentHistory.mockResolvedValue({ agent_id: 'default', history: [] })
  mockedFetchSkills.mockResolvedValue({ pool: [], workspace: [{ name: 'demo', description: '', path: '', source: '', enabled: true, languages: [], metadata: {} }] })
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
  it('展示 Agent 列表与详情并使用真实 API 数据', async () => {
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
    await waitFor(() => expect(screen.getByText(/openai\/gpt-5/)).toBeInTheDocument())
    expect(screen.getByText('SQLite')).toBeInTheDocument()
    expect(screen.getByText('1 已启用')).toBeInTheDocument()
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

    await waitFor(() => expect(screen.getByText(/openai\/gpt-5/)).toBeInTheDocument())
    expect(mockedFetchAgent).toHaveBeenCalledTimes(2)
    expect(mockedFetchAgent).toHaveBeenLastCalledWith('default')
  })
})
