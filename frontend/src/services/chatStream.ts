import { parseSSEBlocks, type ParsedSSEBlock } from './sse'

const API_BASE = '/api/v1'

export interface StreamEnvelope {
  event: 'update' | 'done' | 'error' | 'interrupt' | 'command' | string
  data: unknown
  version: string
  thread_id: string
  agent_id: string
  trace_id: string
  run_id: string
}

export interface RunCancelResult {
  cancelled: boolean
  status: string
  agent_id: string
  thread_id: string
  run_id: string
  detail: string
}

export interface StreamStopResult {
  localStopped: true
  serverCancelled: boolean
  detail: string
}

export interface StreamControl {
  threadId: string
  abort: () => void
  stop: () => Promise<StreamStopResult>
}

export async function cancelAgentRun(
  agentId: string,
  threadId: string,
  runId = '',
): Promise<RunCancelResult> {
  const res = await fetch(`${API_BASE}/agent/runs/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, thread_id: threadId, run_id: runId }),
  })
  if (!res.ok) {
    let detail = await res.text()
    try {
      detail = String((JSON.parse(detail) as { detail?: unknown }).detail ?? detail)
    } catch {
      // Keep the response text when it is not JSON.
    }
    throw new Error(detail)
  }
  return res.json()
}

export function normalizeStreamEnvelope(block: ParsedSSEBlock): StreamEnvelope {
  const raw = block.data
  if (raw && typeof raw === 'object' && 'version' in raw && 'event' in raw) {
    return raw as StreamEnvelope
  }
  const legacy = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  return {
    event: block.event,
    data: raw,
    version: 'legacy',
    thread_id: String(legacy.thread_id ?? ''),
    agent_id: String(legacy.agent_id ?? 'default'),
    trace_id: String(legacy.trace_id ?? ''),
    run_id: String(legacy.run_id ?? ''),
  }
}

export function streamChat(
  message: string,
  threadId: string | undefined,
  agentId: string,
  source: string,
  lang: string | undefined,
  onEvent: (data: StreamEnvelope) => void,
  onDone: () => void,
  onError: (err: string) => void,
  extras?: {
    attachments?: Array<{
      filename: string
      relative_path?: string
      mime_type: string
      size: number
      kind: 'text' | 'image' | 'binary'
      content_base64: string
    }>
    attachment_ids?: string[]
    provider?: string
    model?: string
  },
): StreamControl {
  const controller = new AbortController()
  const effectiveThreadId = threadId ?? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
  let latestRunId = ''
  let terminal = false

  const fail = (message: string) => {
    if (terminal) return
    terminal = true
    onError(message)
  }
  const finish = () => {
    if (terminal) return
    terminal = true
    onDone()
  }

  fetch(`${API_BASE}/agent/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(lang ? { 'Accept-Language': lang } : {}),
    },
    body: JSON.stringify({
      message,
      thread_id: effectiveThreadId,
      agent_id: agentId,
      source,
      lang,
      attachments: extras?.attachments ?? [],
      attachment_ids: extras?.attachment_ids ?? [],
      provider: extras?.provider,
      model: extras?.model,
    }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) {
      fail(await res.text())
      return
    }
    const reader = res.body?.getReader()
    if (!reader) {
      fail('服务未返回可读取的流')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    const dispatch = (blocks: ParsedSSEBlock[]) => {
      for (const block of blocks) {
        const envelope = normalizeStreamEnvelope(block)
        if (envelope.run_id) latestRunId = envelope.run_id
        if (envelope.event === 'error') {
          const detail = envelope.data as { error?: unknown }
          fail(String(detail?.error ?? '流式服务错误'))
          return
        }
        onEvent(envelope)
        if (envelope.event === 'done') {
          finish()
          return
        }
      }
    }

    while (!terminal) {
      const { done, value } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        const parsed = parseSSEBlocks(buffer, true)
        dispatch(parsed.events)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const parsed = parseSSEBlocks(buffer)
      buffer = parsed.remainder
      dispatch(parsed.events)
    }
    if (!terminal) fail('流式连接在完成事件前中断')
  }).catch((err) => {
    if (err.name !== 'AbortError') fail(String(err))
  })

  return {
    threadId: effectiveThreadId,
    abort: () => controller.abort(),
    stop: async () => {
      controller.abort()
      try {
        const result = await cancelAgentRun(agentId, effectiveThreadId, latestRunId)
        return {
          localStopped: true,
          serverCancelled: result.cancelled,
          detail: result.detail,
        }
      } catch (err) {
        return {
          localStopped: true,
          serverCancelled: false,
          detail: err instanceof Error ? err.message : String(err),
        }
      }
    },
  }
}
