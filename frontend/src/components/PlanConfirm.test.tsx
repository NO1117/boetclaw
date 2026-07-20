import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlanConfirm from './PlanConfirm'
import { confirmPlan, type ExecutionRef } from '../services/api'

vi.mock('../services/api', () => ({
  confirmPlan: vi.fn(),
}))

const ref: ExecutionRef = {
  agent_id: 'workspace-original',
  thread_id: 'thread-original',
  checkpoint_ns: 'plan',
  interrupt_id: 'interrupt-original',
  interrupt_type: 'plan_confirm',
}

beforeEach(() => {
  vi.mocked(confirmPlan).mockReset()
})

describe('PlanConfirm', () => {
  it('提交服务端原始 ExecutionRef 并显示成功响应', async () => {
    vi.mocked(confirmPlan).mockResolvedValueOnce({ response: '服务端继续执行' })
    const onResolved = vi.fn()
    render(<PlanConfirm executionRef={ref} todos={['检查井况']} onResolved={onResolved} />)

    expect(screen.getByText(/原 Agent：workspace-original/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /批准执行/ }))

    await waitFor(() => expect(confirmPlan).toHaveBeenCalledWith(ref, 'approve', undefined))
    expect(onResolved).toHaveBeenCalledWith('服务端继续执行')
  })

  it('失败时保留卡片并展示可见错误', async () => {
    vi.mocked(confirmPlan).mockRejectedValueOnce(new Error('checkpoint 已失效'))
    render(<PlanConfirm executionRef={ref} todos={[]} onResolved={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /拒绝/ }))

    expect(await screen.findByText(/计划确认失败.*checkpoint 已失效/)).toBeVisible()
    expect(screen.getByRole('button', { name: /批准执行/ })).toBeEnabled()
  })
})
