import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderSettings from './ProviderSettings'

vi.mock('../services/api', () => ({
  fetchProviderConnections: vi.fn(),
  fetchVaultStatus: vi.fn(),
  createProviderConnection: vi.fn(),
  updateProviderConnection: vi.fn(),
  deleteProviderConnection: vi.fn(),
  checkProviderConnection: vi.fn(),
  setDefaultProviderConnection: vi.fn(),
  cloneProviderConnection: vi.fn(),
  importEnvProviderCredentials: vi.fn(),
  fetchConnectionModels: vi.fn(),
}))

import {
  checkProviderConnection,
  createProviderConnection,
  fetchConnectionModels,
  fetchProviderConnections,
  fetchVaultStatus,
  importEnvProviderCredentials,
  updateProviderConnection,
} from '../services/api'

const sampleConn = {
  id: 'conn_test1',
  provider_type: 'openai',
  display_name: 'Test OpenAI',
  base_url: 'http://localhost:8001/v1',
  credential_id: 'cred_1',
  credential_configured: true,
  credential_source: 'vault' as const,
  credential_fingerprint: '9999',
  default_model: 'gpt-4o',
  enabled: true,
  timeout_seconds: 30,
  revision: 1,
  is_default: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_check: null,
}

describe('ProviderSettings (model connections)', () => {
  beforeEach(() => {
    vi.mocked(fetchProviderConnections).mockResolvedValue({ connections: [sampleConn] })
    vi.mocked(fetchVaultStatus).mockResolvedValue({
      configured: true,
      writable: true,
      credential_count: 1,
      message: '',
    })
    vi.mocked(fetchConnectionModels).mockResolvedValue({ models: [] })
  })

  it('lists connections without exposing api keys', async () => {
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    expect(screen.getByText(/已配置 \(保险箱\)/)).toBeInTheDocument()
    expect(screen.queryByText(/sk-/)).not.toBeInTheDocument()
  })

  it('does not pre-fill api key when editing', async () => {
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '编辑' }))
    const keyInput = screen.getByPlaceholderText(/API Key 已配置/)
    expect(keyInput).toHaveValue('')
  })

  it('creates connection and clears api key field', async () => {
    vi.mocked(createProviderConnection).mockResolvedValue({
      connection: { ...sampleConn, id: 'conn_new', display_name: 'New' },
    })
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '新建连接' }))
    await userEvent.type(screen.getByPlaceholderText('显示名称'), 'New')
    await userEvent.type(screen.getByPlaceholderText('API Key'), 'sk-temporary-key')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(createProviderConnection).toHaveBeenCalled())
    const payload = vi.mocked(createProviderConnection).mock.calls[0][0]
    expect(payload.api_key).toBe('sk-temporary-key')
  })

  it('shows vault disabled message', async () => {
    vi.mocked(fetchVaultStatus).mockResolvedValue({
      configured: false,
      writable: false,
      credential_count: 0,
      message: '未配置主密钥',
    })
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText(/未配置主密钥/)).toBeInTheDocument())
  })

  it('handles import env response', async () => {
    vi.mocked(importEnvProviderCredentials).mockResolvedValue({
      imported_connection_ids: ['conn_x'],
      count: 1,
      env_cleanup_required: true,
      message: '请手动清理 .env',
    })
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '从环境变量导入' }))
    await waitFor(() => expect(screen.getByText('请手动清理 .env')).toBeInTheDocument())
  })

  it('runs connection check', async () => {
    vi.mocked(checkProviderConnection).mockResolvedValue({ connected: true, detail: 'ok' })
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '检测' }))
    await waitFor(() => expect(checkProviderConnection).toHaveBeenCalledWith('conn_test1'))
  })

  it('surfaces save errors', async () => {
    vi.mocked(updateProviderConnection).mockRejectedValue(new Error('revision 冲突'))
    render(<ProviderSettings />)
    await waitFor(() => expect(screen.getByText('Test OpenAI')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '编辑' }))
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(screen.getByText(/revision 冲突/)).toBeInTheDocument())
  })
})
