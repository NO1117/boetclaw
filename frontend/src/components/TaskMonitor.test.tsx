import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TaskMonitor from './TaskMonitor'
import * as api from '../services/api'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    fetchTasksPaged: vi.fn(),
    fetchTaskQueueStats: vi.fn(),
    controlTaskQueue: vi.fn(),
    createTaskAdvanced: vi.fn(),
    openTaskEventsStream: vi.fn(() => () => {}),
  }
})

const mockedPaged = vi.mocked(api.fetchTasksPaged)
const mockedStats = vi.mocked(api.fetchTaskQueueStats)
const mockedControl = vi.mocked(api.controlTaskQueue)

afterEach(() => {
  vi.clearAllMocks()
})

describe('TaskMonitor runtime center', () => {
  it('renders queue stats and tasks', async () => {
    mockedStats.mockResolvedValue({
      queue_depth: 2,
      status_counts: { queued: 2, running: 1 },
      dead_letter_count: 0,
      retry_total: 0,
      lease_reclaimed_total: 0,
      paused: false,
    })
    mockedPaged.mockResolvedValue({
      items: [{
        id: 'task-1',
        title: '测试任务',
        prompt: 'do work',
        status: 'pending',
        thread_id: 't1',
        trace_id: '',
        run_id: '',
        result: '',
        error: '',
        gateway: '',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }],
      next_cursor: null,
    })

    render(<TaskMonitor onSelectTask={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('运行中心')).toBeInTheDocument()
      expect(screen.getByText('测试任务')).toBeInTheDocument()
      expect(screen.getByText(/深度 2/)).toBeInTheDocument()
    })
  })

  it('can pause queue from header control', async () => {
    mockedStats.mockResolvedValue({
      queue_depth: 0,
      status_counts: {},
      dead_letter_count: 0,
      retry_total: 0,
      lease_reclaimed_total: 0,
      paused: false,
    })
    mockedPaged.mockResolvedValue({ items: [], next_cursor: null })
    mockedControl.mockResolvedValue({
      queue_depth: 0,
      status_counts: {},
      dead_letter_count: 0,
      retry_total: 0,
      lease_reclaimed_total: 0,
      paused: true,
    })

    render(<TaskMonitor onSelectTask={() => {}} />)
    await waitFor(() => expect(screen.getByText('暂停')).toBeInTheDocument())
    await userEvent.click(screen.getByText('暂停'))
    await waitFor(() => expect(mockedControl).toHaveBeenCalledWith(true))
  })
})
