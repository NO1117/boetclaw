import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPanel from './ChatPanel'
import { streamChat, type StreamControl } from '../services/api'

vi.mock('../services/api', () => ({
  sendChat: vi.fn(),
  streamChat: vi.fn(),
  fetchApprovals: vi.fn(),
  resumeApproval: vi.fn(),
  confirmPlan: vi.fn(),
}))

beforeEach(() => {
  vi.mocked(streamChat).mockReset()
})

describe('ChatPanel', () => {
  it('停止流时调用 abort+服务端取消控制并展示确认结果', async () => {
    const stop = vi.fn().mockResolvedValue({
      localStopped: true,
      serverCancelled: true,
      detail: 'cancelled',
    })
    const control: StreamControl = {
      threadId: 'thread-1',
      abort: vi.fn(),
      stop,
    }
    vi.mocked(streamChat).mockReturnValue(control)
    render(
      <ChatPanel
        threadId={null}
        agentId="workspace-a"
        onThreadId={vi.fn()}
        onTraceUpdate={vi.fn()}
      />,
    )

    const input = screen.getByPlaceholderText(/输入任务描述/)
    await userEvent.type(input, '停止这个任务{enter}')
    await userEvent.click(screen.getByTitle('停止运行'))

    expect(stop).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('已停止本地流读取；服务端已确认取消。')).toBeVisible()
  })
})
