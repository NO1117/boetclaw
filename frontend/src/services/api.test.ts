import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cancelAgentRun,
  confirmPlan,
  archiveChatSession,
  deleteArtifact,
  deleteChatSession,
  deleteDailyReport,
  fetchChatSessions,
  unarchiveChatSession,
  fetchArtifacts,
  fetchConsoleAuthStatus,
  normalizeStreamEnvelope,
  resumeApproval,
  streamChat,
  updateDailyReport,
  type ExecutionRef,
} from './api'
import {
  fetchMock,
  installFetchMock,
  mockJson,
  mockStream,
  mockText,
} from '../test/fetchMock'

const executionRef: ExecutionRef = {
  agent_id: 'workspace-a',
  thread_id: 'thread-1',
  checkpoint_ns: 'plan',
  interrupt_id: 'interrupt-1',
  interrupt_type: 'plan_confirm',
}

beforeEach(() => {
  fetchMock.mockReset()
  installFetchMock()
})

describe('恢复和领域 API 请求', () => {
  it('计划确认原样传递服务端 ExecutionRef', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ response: '继续执行' }))

    await confirmPlan(executionRef, 'edit', ['步骤一'])

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/agent/plan/confirm', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        execution_ref: executionRef,
        decision: 'edit',
        edited_todos: ['步骤一'],
      }),
    }))
  })

  it('审批恢复传递审批 id、完整引用和决定', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ status: 'approved' }))

    await resumeApproval('approval-1', executionRef, 'approve')

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      approval_id: 'approval-1',
      execution_ref: executionRef,
      decision: 'approve',
    })
  })

  it('领域更新和删除使用正确请求契约', async () => {
    fetchMock
      .mockResolvedValueOnce(mockJson({ id: 'report-1', summary: '已更新' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await updateDailyReport('report-1', { summary: '已更新' })
    await deleteDailyReport('report-1')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/domain/reports/report-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ summary: '已更新' }),
      credentials: 'include',
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/domain/reports/report-1', expect.objectContaining({
      method: 'DELETE',
      credentials: 'include',
    }))
  })

  it('会话删除使用正确请求契约', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ deleted: 'thread-1' }))

    await deleteChatSession('thread-1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/agent/sessions/thread-1',
      expect.objectContaining({ method: 'DELETE', credentials: 'include' }),
    )
  })

  it('会话归档与列表过滤使用正确请求契约', async () => {
    fetchMock
      .mockResolvedValueOnce(mockJson({ thread_id: 'thread-1', archived: true, archived_at: '2026-07-17T00:00:00Z' }))
      .mockResolvedValueOnce(mockJson({ thread_id: 'thread-1', archived: false, archived_at: '' }))
      .mockResolvedValueOnce(mockJson({ sessions: [] }))

    await archiveChatSession('thread-1')
    await unarchiveChatSession('thread-1')
    await fetchChatSessions('well', 20, { archivedOnly: true })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/agent/sessions/thread-1/archive', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/agent/sessions/thread-1/unarchive', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/v1/agent/sessions?q=well&limit=20&archived_only=true', expect.objectContaining({
      credentials: 'include',
    }))
  })

  it('产物删除使用正确请求契约并编码文件名', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ deleted: 'demo chart.png', kind: 'chart' }))

    await deleteArtifact('chart', 'demo chart.png')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/artifacts/chart/demo%20chart.png',
      expect.objectContaining({ method: 'DELETE', credentials: 'include' }),
    )
  })

  it('产物列表保留 sha256 字段', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({
      artifacts: [{
        id: 'code:demo.py',
        kind: 'code',
        filename: 'demo.py',
        size: 12,
        created_at: '',
        task_id: '',
        trace_id: '',
        agent_id: '',
        well_id: '',
        sha256: 'abc123',
        preview: 'print(1)',
        url: '/api/v1/files/code/demo.py',
        download_url: '/api/v1/files/artifacts/code/demo.py/download',
      }],
    }))

    const data = await fetchArtifacts('code')

    expect(data.artifacts[0].sha256).toBe('abc123')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/artifacts?kind=code',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('鉴权错误保留服务端可见信息', async () => {
    fetchMock.mockResolvedValueOnce(mockText('认证已过期', 401))

    await expect(fetchConsoleAuthStatus()).rejects.toThrow('认证已过期')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/status',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('网络错误向调用方传播', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(confirmPlan(executionRef, 'approve')).rejects.toThrow('Failed to fetch')
  })

  it('取消错误优先提取 JSON detail', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ detail: '运行不存在' }, 404))
    await expect(cancelAgentRun('a', 't', 'r')).rejects.toThrow('运行不存在')
  })

  it('取消错误在非 JSON 响应时保留原文', async () => {
    fetchMock.mockResolvedValueOnce(mockText('gateway unavailable', 502))
    await expect(cancelAgentRun('a', 't')).rejects.toThrow('gateway unavailable')
  })
})

describe('streamChat', () => {
  it('将旧版事件规范化为统一 envelope', () => {
    expect(normalizeStreamEnvelope({
      event: 'update',
      data: { thread_id: 'legacy-thread', run_id: 'legacy-run' },
    })).toEqual({
      event: 'update',
      data: { thread_id: 'legacy-thread', run_id: 'legacy-run' },
      version: 'legacy',
      thread_id: 'legacy-thread',
      agent_id: 'default',
      trace_id: '',
      run_id: 'legacy-run',
    })
  })

  it('跨网络分块解析 CRLF，并且 done 只通知一次', async () => {
    fetchMock.mockResolvedValueOnce(mockStream([
      'event: update\r\ndata: {"version":"1","event":"update","data":{"data":{"type":"message",',
      '"content":"你好"}},"thread_id":"thread-1","agent_id":"a","trace_id":"trace-1","run_id":"run-1"}\r\n\r\n',
      'event: done\r\ndata: {"version":"1","event":"done","data":{},"thread_id":"thread-1","agent_id":"a","trace_id":"trace-1","run_id":"run-1"}\r\n\r\n',
      'event: done\r\ndata: {"version":"1","event":"done","data":{},"thread_id":"thread-1","agent_id":"a","trace_id":"trace-1","run_id":"run-1"}\r\n\r\n',
    ]))
    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    streamChat('消息', 'thread-1', 'a', 'user', 'zh-CN', onEvent, onDone, onError)

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onError).not.toHaveBeenCalled()
  })

  it('error envelope 只报告错误，不报告完成', async () => {
    fetchMock.mockResolvedValueOnce(mockStream([
      'event: error\n'
      + 'data: {"version":"1","event":"error","data":{"error":"provider down"},'
      + '"thread_id":"thread-1","agent_id":"a","trace_id":"trace-1","run_id":"run-1"}\n\n',
    ]))
    const onDone = vi.fn()
    const onError = vi.fn()

    streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), onDone, onError)

    await waitFor(() => expect(onError).toHaveBeenCalledWith('provider down'))
    expect(onDone).not.toHaveBeenCalled()
  })

  it('连接无 done 时报告协议中断', async () => {
    fetchMock.mockResolvedValueOnce(mockStream([
      'event: update\n'
      + 'data: {"version":"1","event":"update","data":{},'
      + '"thread_id":"thread-1","agent_id":"a","trace_id":"","run_id":"run-1"}\n\n',
    ]))
    const onError = vi.fn()

    streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), vi.fn(), onError)

    await waitFor(() => expect(onError).toHaveBeenCalledWith('流式连接在完成事件前中断'))
  })

  it('HTTP 错误和空响应体均给出可见错误', async () => {
    fetchMock
      .mockResolvedValueOnce(mockText('unauthorized', 401))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
    const authError = vi.fn()
    const bodyError = vi.fn()

    streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), vi.fn(), authError)
    await waitFor(() => expect(authError).toHaveBeenCalledWith('unauthorized'))

    streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), vi.fn(), bodyError)
    await waitFor(() => expect(bodyError).toHaveBeenCalledWith('服务未返回可读取的流'))
  })

  it('stop 先 abort 流，再请求服务端取消', async () => {
    let streamSignal: AbortSignal | undefined
    fetchMock
      .mockImplementationOnce((_input, init) => {
        streamSignal = init?.signal ?? undefined
        return new Promise<Response>((_resolve, reject) => {
          streamSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        })
      })
      .mockResolvedValueOnce(mockJson({
        cancelled: true,
        status: 'cancelled',
        agent_id: 'a',
        thread_id: 'thread-1',
        run_id: '',
        detail: 'cancelled',
      }))

    const control = streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), vi.fn(), vi.fn())
    const result = await control.stop()

    expect(streamSignal?.aborted).toBe(true)
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/agent/runs/cancel', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ agent_id: 'a', thread_id: 'thread-1', run_id: '' }),
    }))
    expect(result).toEqual({
      localStopped: true,
      serverCancelled: true,
      detail: 'cancelled',
    })
  })

  it('stop 在服务端取消失败时仍确认本地停止', async () => {
    fetchMock
      .mockImplementationOnce((_input, init) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }))
      .mockResolvedValueOnce(mockText('cancel endpoint failed', 500))

    const control = streamChat('消息', 'thread-1', 'a', 'user', undefined, vi.fn(), vi.fn(), vi.fn())
    control.abort()
    const result = await control.stop()

    expect(result).toEqual({
      localStopped: true,
      serverCancelled: false,
      detail: 'cancel endpoint failed',
    })
  })
})
