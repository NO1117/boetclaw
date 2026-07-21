import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPanel from './ChatPanel'
import {
  streamChat,
  uploadAgentAttachment,
  fetchAttachmentRecord,
  type StreamControl,
} from '../services/api'

vi.mock('../services/api', () => ({
  sendChat: vi.fn(),
  streamChat: vi.fn(),
  uploadAgentAttachment: vi.fn(),
  fetchAttachmentRecord: vi.fn(),
  retryAgentAttachment: vi.fn(),
  cancelAgentAttachment: vi.fn(),
  deleteAgentAttachment: vi.fn(),
  fetchApprovals: vi.fn(),
  resumeApproval: vi.fn(),
  confirmPlan: vi.fn(),
}))

const readyRecord = {
  attachment_id: 'att-test-1',
  agent_id: 'default',
  filename: 'notes.txt',
  relative_path: '',
  mime_type: 'text/plain',
  size: 5,
  kind: 'text' as const,
  status: 'ready' as const,
  scan_status: 'unscanned' as const,
  error_summary: '',
  summary: { chunk_count: 1, searchable: true, char_count: 5 },
  created_at: '2026-07-21T00:00:00Z',
  updated_at: '2026-07-21T00:00:00Z',
  expires_at: '2026-08-21T00:00:00Z',
}

beforeEach(() => {
  vi.mocked(streamChat).mockReset()
  vi.mocked(uploadAgentAttachment).mockReset()
  vi.mocked(fetchAttachmentRecord).mockReset()
  vi.mocked(uploadAgentAttachment).mockResolvedValue({ ...readyRecord, status: 'uploaded' })
  vi.mocked(fetchAttachmentRecord).mockResolvedValue(readyRecord)
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

    const input = screen.getByLabelText('消息输入')
    await userEvent.type(input, '停止这个任务')
    await userEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await userEvent.click(screen.getByLabelText('停止运行'))

    expect(stop).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('已停止本地流读取；服务端已确认取消。')).toBeVisible()
  })

  it('attachment-only send uses attachment_ids after upload becomes ready', async () => {
    const control: StreamControl = {
      threadId: 'thread-2',
      abort: vi.fn(),
      stop: vi.fn(),
    }
    vi.mocked(streamChat).mockImplementation((
      _message,
      _threadId,
      _agentId,
      _source,
      _lang,
      onEvent,
      onDone,
    ) => {
      queueMicrotask(() => {
        onEvent({
          event: 'done',
          data: { response: 'ok' },
          version: '1',
          thread_id: 'thread-2',
          agent_id: 'default',
          trace_id: 'trace-2',
          run_id: 'run-2',
        })
        onDone()
      })
      return control
    })

    const { container } = render(
      <ChatPanel
        threadId={null}
        agentId="default"
        onThreadId={vi.fn()}
        onTraceUpdate={vi.fn()}
        modelSelection={{ provider: 'openai', model: 'gpt-4o', supportsVision: true, label: 'openai / gpt-4o' }}
      />,
    )

    const fileInput = container.querySelector('input[type="file"]:not([accept])') as HTMLInputElement
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    await userEvent.upload(fileInput, file)
    await waitFor(() => expect(screen.getByLabelText('附件队列')).toHaveTextContent('notes.txt'))
    await waitFor(() => expect(screen.getByRole('button', { name: '发送消息' })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => {
      expect(streamChat).toHaveBeenCalledWith(
        '',
        undefined,
        'default',
        'user',
        expect.any(String),
        expect.any(Function),
        expect.any(Function),
        expect.any(Function),
        expect.objectContaining({
          provider: 'openai',
          model: 'gpt-4o',
          attachment_ids: ['att-test-1'],
        }),
      )
    })
  })

  it('shows unsupported speech state when SpeechRecognition is unavailable', () => {
    render(
      <ChatPanel
        threadId={null}
        agentId="default"
        onThreadId={vi.fn()}
        onTraceUpdate={vi.fn()}
      />,
    )
    expect(screen.getByText(/不支持 Web Speech API/)).toBeVisible()
    expect(screen.getByRole('button', { name: '语音输入' })).toBeDisabled()
  })
})
