import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApprovalCard from './ApprovalCard'
import {
  fetchApprovals,
  resumeApproval,
  type ApprovalRequest,
  type ExecutionRef,
} from '../services/api'
import { deferred } from '../test/fetchMock'

vi.mock('../services/api', () => ({
  fetchApprovals: vi.fn(),
  resumeApproval: vi.fn(),
}))

const ref: ExecutionRef = {
  agent_id: 'workspace-a',
  thread_id: 'thread-a',
  checkpoint_ns: 'tools',
  interrupt_id: 'tool-call-1',
  interrupt_type: 'tool_approval',
}

function approval(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    id: 'approval-1',
    tool: 'write_file',
    args: { path: 'report.md' },
    findings: [{
      severity: 'high',
      category: 'write',
      message: '写文件',
      guardian: 'tool-guard',
    }],
    thread_id: 'thread-a',
    execution_ref: ref,
    status: 'pending',
    decision: '',
    error: '',
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(fetchApprovals).mockReset()
  vi.mocked(resumeApproval).mockReset()
})

describe('ApprovalCard', () => {
  it('区分 pending、resuming 和不可恢复状态', async () => {
    vi.mocked(fetchApprovals).mockResolvedValue({
      pending: [
        approval(),
        approval({ id: 'approval-2', status: 'resuming' }),
        approval({ id: 'approval-3', execution_ref: null }),
      ],
    })

    render(<ApprovalCard />)

    expect(await screen.findByText(/正在恢复原执行图/)).toBeVisible()
    expect(screen.getByText(/历史审批缺少执行引用/)).toBeVisible()
    const approveButtons = screen.getAllByRole('button', { name: /批准/ })
    expect(approveButtons[0]).toBeEnabled()
    expect(approveButtons[1]).toBeDisabled()
    expect(approveButtons[2]).toBeDisabled()
  })

  it('恢复期间禁用按钮，重复点击只提交一次', async () => {
    const pendingResume = deferred<unknown>()
    vi.mocked(fetchApprovals).mockResolvedValue({ pending: [approval()] })
    vi.mocked(resumeApproval).mockReturnValue(pendingResume.promise)
    render(<ApprovalCard />)

    const approve = await screen.findByRole('button', { name: /批准/ })
    await userEvent.click(approve)
    expect(approve).toBeDisabled()
    await userEvent.click(approve)

    expect(resumeApproval).toHaveBeenCalledTimes(1)
    expect(resumeApproval).toHaveBeenCalledWith('approval-1', ref, 'approve')
    pendingResume.resolve({})
    await waitFor(() => expect(approve).toBeEnabled())
  })

  it('恢复失败对用户可见', async () => {
    vi.mocked(fetchApprovals).mockResolvedValue({ pending: [approval()] })
    vi.mocked(resumeApproval).mockRejectedValueOnce(new Error('恢复冲突'))
    render(<ApprovalCard />)

    await userEvent.click(await screen.findByRole('button', { name: /拒绝/ }))

    expect(await screen.findByText(/审批恢复失败.*恢复冲突/)).toBeVisible()
  })
})
