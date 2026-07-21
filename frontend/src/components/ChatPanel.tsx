import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Bot,
  Copy,
  FolderOpen,
  ImagePlus,
  Loader2,
  Mic,
  MicOff,
  Paperclip,
  Send,
  Square,
  User,
  Volume2,
  X,
} from 'lucide-react'
import {
  sendChat,
  streamChat,
  uploadAgentAttachment,
  fetchAttachmentRecord,
  retryAgentAttachment,
  cancelAgentAttachment,
  type ChatMessage,
  type ExecutionRef,
  type StreamControl,
  type AttachmentRecordDto,
  type RunMetricsSummary,
  type MemoryCandidateDto,
  type MemoryContextSummary,
  type MemoryActionDto,
} from '../services/api'
import type { ModelSelection } from './ModelSelector'
import PlanConfirm from './PlanConfirm'
import ApprovalCard from './ApprovalCard'
import MemoryCandidateBar from './MemoryCandidateBar'
import {
  ATTACHMENT_LIMITS,
  attachmentIdsForRequest,
  documentSummaryLabel,
  filesToQueue,
  formatBytes,
  isAttachmentSendReady,
  parseAttachmentSummariesFromContent,
  pollAttachmentUntilReady,
  scanStatusLabel,
  stripAttachmentSummaryLines,
  validateQueue,
  type QueuedAttachment,
} from '../utils/attachments'
import {
  getSpeechRecognitionCtor,
} from '../utils/speechInput'
import {
  VoiceInputController,
  formatRecordingDuration,
  voiceInputBusy,
  voiceStatusLabel,
  type VoiceInputMode,
  type VoiceInputState,
} from '../utils/voiceInput'
import {
  VoicePlaybackController,
  type VoiceOutputMode,
  type VoicePlaybackProgress,
} from '../utils/voiceOutput'
import MessageVoicePlayer from './MessageVoicePlayer'
import type { VoiceCapabilities } from '../services/api'
import './ChatPanel.css'
import './MessageVoicePlayer.css'

interface Props {
  threadId: string | null
  agentId: string
  onThreadId: (id: string) => void
  onTraceUpdate: (traceId: string, runId: string) => void
  onRunMetrics?: (metrics: RunMetricsSummary) => void
  onRunStarted?: () => void
  initialMessages?: ChatMessage[]
  historyVersion?: number
  modelSelection?: ModelSelection | null
  onComposerAttachmentsChange?: (count: number, items: Array<{ kind: string }>) => void
  onMemoryContext?: (summary: MemoryContextSummary | null) => void
}

interface PlanPending {
  executionRef: ExecutionRef
  todos: unknown[]
}

const QUICK_PROMPTS = [
  '梳理产品需求并输出开发计划',
  '审查代码变更并列出修复建议',
  '整理周报要点与待办事项',
  '分析界面截图中的信息架构',
]

function formatSpeechDuration(seconds: number): string {
  return formatRecordingDuration(seconds)
}

function resolveStreamTerminalPayload(data: unknown): Record<string, unknown> | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  const payload = data as Record<string, unknown>
  const nested = payload.data
  if (
    nested &&
    typeof nested === 'object' &&
    !Array.isArray(nested) &&
    (
      'memory_context' in nested ||
      'memory_candidates' in nested ||
      'memory_actions' in nested ||
      'response' in nested ||
      'run_metrics' in nested
    )
  ) {
    return nested as Record<string, unknown>
  }
  return payload
}

export default function ChatPanel({
  threadId,
  agentId,
  onThreadId,
  onTraceUpdate,
  onRunMetrics,
  onRunStarted,
  initialMessages = [],
  historyVersion = 0,
  modelSelection = null,
  onComposerAttachmentsChange,
  onMemoryContext,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<QueuedAttachment[]>([])
  const [savedAttachments, setSavedAttachments] = useState<AttachmentRecordDto[]>([])
  const [attachmentError, setAttachmentError] = useState('')
  const [sendError, setSendError] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [useStream, setUseStream] = useState(true)
  const [planPending, setPlanPending] = useState<PlanPending | null>(null)
  const [memoryCandidates, setMemoryCandidates] = useState<MemoryCandidateDto[]>([])
  const applyMemoryPayload = useCallback((payload: Record<string, unknown> | null | undefined) => {
    const summary = payload?.memory_context as MemoryContextSummary | undefined
    const candidates = payload?.memory_candidates as MemoryCandidateDto[] | undefined
    const actions = payload?.memory_actions as MemoryActionDto[] | undefined
    onMemoryContext?.(summary ?? null)
    if (candidates?.length) {
      setMemoryCandidates(prev => {
        const ids = new Set(prev.map(item => item.id))
        return [...prev, ...candidates.filter(item => !ids.has(item.id))]
      })
    }
    if (actions?.length) {
      setMessages(prev => [
        ...prev,
        ...actions
          .filter(action => action.message)
          .map(action => ({
            role: 'assistant' as const,
            content: `记忆：${action.message}`,
          })),
      ])
    }
  }, [onMemoryContext])
  const [approvalPending, setApprovalPending] = useState(false)
  const [speechState, setSpeechState] = useState<VoiceInputState>(
    getSpeechRecognitionCtor() ? 'idle' : 'unsupported',
  )
  const [voiceInputMode, setVoiceInputMode] = useState<VoiceInputMode>('none')
  const [voiceCaps, setVoiceCaps] = useState<VoiceCapabilities | null>(null)
  const [voiceError, setVoiceError] = useState('')
  const [speechSeconds, setSpeechSeconds] = useState(0)
  const [speechPreview, setSpeechPreview] = useState('')
  const [activeSpeechMessage, setActiveSpeechMessage] = useState<number | null>(null)
  const [speechPlaybackState, setSpeechPlaybackState] = useState<'idle' | 'playing' | 'paused' | 'unsupported'>(
    'idle',
  )
  const [voiceOutputMode, setVoiceOutputMode] = useState<VoiceOutputMode>('none')
  const [playbackProgress, setPlaybackProgress] = useState<VoicePlaybackProgress>({ current: 0, duration: 0 })
  const [lastVoiceInsert, setLastVoiceInsert] = useState('')

  const bottomRef = useRef<HTMLDivElement>(null)
  const streamControlRef = useRef<StreamControl | null>(null)
  const voiceInputRef = useRef<VoiceInputController | null>(null)
  const speechControllerRef = useRef(new VoicePlaybackController())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, streaming])

  useEffect(() => {
    setMessages(initialMessages.map(msg => ({
      ...msg,
      attachments: msg.attachments ?? parseAttachmentSummariesFromContent(msg.content),
      content: stripAttachmentSummaryLines(msg.content),
    })))
  }, [historyVersion])

  useEffect(() => {
    const items = attachments.map(item => ({ kind: item.kind }))
    onComposerAttachmentsChange?.(attachments.length, items)
  }, [attachments, onComposerAttachmentsChange])

  useEffect(() => {
    const controller = new VoiceInputController({
      onStateChange: setSpeechState,
      onSecondsChange: setSpeechSeconds,
      onPreviewChange: setSpeechPreview,
      onTranscript: (text, mode) => {
        setInput(text)
        setVoiceInputMode(mode)
        const insert = voiceInputRef.current?.getLastInsert() ?? ''
        if (insert) setLastVoiceInsert(insert)
      },
      onError: message => setVoiceError(message),
    })
    voiceInputRef.current = controller
    speechControllerRef.current.setCallbacks(setSpeechPlaybackState, setPlaybackProgress)
    void (async () => {
      const caps = await controller.loadCapabilities()
      setVoiceCaps(caps)
      setVoiceInputMode(controller.getMode())
      await speechControllerRef.current.loadCapabilities()
      setVoiceOutputMode(speechControllerRef.current.mode)
    })()
    return () => {
      controller.dispose()
      speechControllerRef.current.cancel()
    }
  }, [])

  useEffect(() => () => {
    if (streamControlRef.current) void streamControlRef.current.stop()
    voiceInputRef.current?.dispose()
    speechControllerRef.current.cancel()
  }, [])

  const canSend = useMemo(() => {
    if (loading) return false
    const hasText = input.trim().length > 0
    const readyAttachments = attachments.filter(isAttachmentSendReady)
    const pending = attachments.some(item => !['ready', 'failed', 'cancelled', 'error'].includes(item.status))
    if (pending) return false
    return hasText || readyAttachments.length > 0
  }, [attachments, input, loading])

  const visionBlocked = useMemo(() => {
    if (!modelSelection) return false
    return attachments.some(a => a.kind === 'image' && isAttachmentSendReady(a)) && !modelSelection.supportsVision
  }, [attachments, modelSelection])

  const startUpload = useCallback(async (item: QueuedAttachment) => {
    const controller = new AbortController()
    setAttachments(prev => prev.map(row =>
      row.id === item.id
        ? { ...row, status: 'uploading', statusMessage: '上传中…', progress: 0, abortController: controller }
        : row,
    ))
    try {
      const record = await uploadAgentAttachment(
        agentId,
        item.file,
        item.relativePath,
        progress => {
          setAttachments(prev => prev.map(row =>
            row.id === item.id ? { ...row, progress, statusMessage: `上传中 ${progress}%` } : row,
          ))
        },
        controller.signal,
      )
      setAttachments(prev => prev.map(row =>
        row.id === item.id
          ? {
              ...row,
              attachmentId: record.attachment_id,
              record,
              status: record.status === 'ready' ? 'ready' : 'parsing',
              statusMessage: record.status === 'ready' ? scanStatusLabel(record.scan_status) : '解析中…',
              progress: 100,
            }
          : row,
      ))
      if (record.status !== 'ready' && record.status !== 'failed') {
        const finalRecord = await pollAttachmentUntilReady(
          id => fetchAttachmentRecord(agentId, id),
          record.attachment_id,
          updated => {
            setAttachments(prev => prev.map(row =>
              row.id === item.id
                ? {
                    ...row,
                    record: updated,
                    status: updated.status as QueuedAttachment['status'],
                    statusMessage: updated.status === 'ready'
                      ? `${documentSummaryLabel(updated) || '解析完成'} · ${scanStatusLabel(updated.scan_status)}`
                      : updated.status === 'failed'
                        ? updated.error_summary || '解析失败'
                        : '解析中…',
                  }
                : row,
            ))
          },
        )
        setSavedAttachments(prev => {
          const next = prev.filter(row => row.attachment_id !== finalRecord.attachment_id)
          return [finalRecord, ...next].slice(0, 20)
        })
        setAttachments(prev => prev.map(row =>
          row.id === item.id
            ? {
                ...row,
                record: finalRecord,
                status: finalRecord.status === 'ready' ? 'ready' : 'failed',
                statusMessage: finalRecord.status === 'ready'
                  ? `${documentSummaryLabel(finalRecord) || '解析完成'} · ${scanStatusLabel(finalRecord.scan_status)}`
                  : finalRecord.error_summary || '解析失败',
              }
            : row,
        ))
      } else {
        setSavedAttachments(prev => [record, ...prev.filter(row => row.attachment_id !== record.attachment_id)].slice(0, 20))
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setAttachments(prev => prev.map(row =>
        row.id === item.id
          ? { ...row, status: message.includes('取消') ? 'cancelled' : 'error', statusMessage: message }
          : row,
      ))
      if (!message.includes('取消')) setAttachmentError(message)
    }
  }, [agentId])

  useEffect(() => {
    for (const item of attachments) {
      if (item.status === 'pending') void startUpload(item)
    }
  }, [attachments, startUpload])

  const addFiles = useCallback(async (files: FileList | File[]) => {
    setAttachmentError('')
    const { queue, errors } = await filesToQueue(files)
    if (errors.length) setAttachmentError(errors.join('；'))
    setAttachments(prev => {
      const merged = [...prev]
      for (const item of queue) {
        if (merged.some(existing => existing.id === item.id)) continue
        merged.push(item)
      }
      const limitError = validateQueue(merged)
      if (limitError) {
        setAttachmentError(limitError)
        return prev
      }
      return merged
    })
  }, [])

  const removeAttachment = (id: string) => {
    setAttachments(prev => {
      const target = prev.find(item => item.id === id)
      target?.abortController?.abort()
      return prev.filter(item => item.id !== id)
    })
    setAttachmentError('')
  }

  const retryAttachment = async (id: string) => {
    const target = attachments.find(item => item.id === id)
    if (!target?.attachmentId) return
    try {
      await retryAgentAttachment(agentId, target.attachmentId)
      setAttachments(prev => prev.map(row =>
        row.id === id ? { ...row, status: 'parsing', statusMessage: '重新解析中…' } : row,
      ))
      const finalRecord = await pollAttachmentUntilReady(
        attachmentId => fetchAttachmentRecord(agentId, attachmentId),
        target.attachmentId,
        updated => {
          setAttachments(prev => prev.map(row =>
            row.id === id
              ? {
                  ...row,
                  record: updated,
                  status: updated.status as QueuedAttachment['status'],
                  statusMessage: updated.error_summary || updated.status,
                }
              : row,
          ))
        },
      )
      setAttachments(prev => prev.map(row =>
        row.id === id
          ? {
              ...row,
              record: finalRecord,
              status: finalRecord.status === 'ready' ? 'ready' : 'failed',
              statusMessage: finalRecord.status === 'ready' ? '解析完成' : finalRecord.error_summary,
            }
          : row,
      ))
    } catch (err) {
      setAttachmentError(err instanceof Error ? err.message : String(err))
    }
  }

  const cancelAttachmentUpload = async (id: string) => {
    const target = attachments.find(item => item.id === id)
    target?.abortController?.abort()
    if (target?.attachmentId) {
      try {
        await cancelAgentAttachment(agentId, target.attachmentId)
      } catch {
        // Local cancel still removes queue item.
      }
    }
    setAttachments(prev => prev.filter(item => item.id !== id))
  }

  const reuseSavedAttachment = (record: AttachmentRecordDto) => {
    if (attachments.some(item => item.attachmentId === record.attachment_id)) return
    const pseudoFile = new File([], record.filename, { type: record.mime_type })
    Object.defineProperty(pseudoFile, 'size', { value: record.size })
    const queueItem: QueuedAttachment = {
      id: `reuse-${record.attachment_id}`,
      localKey: `reuse-${record.attachment_id}`,
      file: pseudoFile,
      relativePath: record.relative_path || record.filename,
      kind: record.kind,
      status: 'ready',
      statusMessage: `${documentSummaryLabel(record) || '已就绪'} · ${scanStatusLabel(record.scan_status)}`,
      mimeType: record.mime_type,
      size: record.size,
      progress: 100,
      attachmentId: record.attachment_id,
      record,
    }
    setAttachments(prev => [...prev, queueItem])
  }

  const stopSpeechInput = () => {
    void voiceInputRef.current?.stop()
  }

  const cancelSpeechInput = () => {
    voiceInputRef.current?.cancel()
    setVoiceError('')
  }

  const toggleSpeechInput = () => {
    void voiceInputRef.current?.toggle(input)
  }

  const undoVoiceInsert = () => {
    if (!voiceInputRef.current || !lastVoiceInsert) return
    setInput(voiceInputRef.current.undoLastInsert(input))
    setLastVoiceInsert('')
  }

  const handleSend = async () => {
    const text = input.trim()
    const readyAttachments = attachments.filter(isAttachmentSendReady)
    if ((!text && readyAttachments.length === 0) || loading) return
    const queueError = validateQueue(attachments)
    if (queueError) {
      setAttachmentError(queueError)
      return
    }
    if (visionBlocked) {
      setSendError('当前模型不支持图像，请切换支持视觉的模型或移除图片。')
      return
    }

    setSendError('')
    setAttachmentError('')
    const attachmentIds = attachmentIdsForRequest(attachments)

    const displayAttachments = readyAttachments.map(item => ({
      filename: item.relativePath || item.file.name,
      sizeLabel: formatBytes(item.size),
      kind: item.kind === 'document' ? 'text' as const : item.kind === 'image' ? 'image' as const : item.kind === 'text' ? 'text' as const : 'binary' as const,
      attachmentId: item.attachmentId,
      citation: item.record?.summary?.searchable ? '已检索引用' : undefined,
    }))

    setMessages(prev => [...prev, {
      role: 'user',
      content: text,
      attachments: displayAttachments,
    }])
    setLoading(true)

    const lang = navigator.language
    const requestExtras = {
      attachment_ids: attachmentIds,
      provider: modelSelection?.provider,
      model: modelSelection?.model,
    }

    const clearComposer = () => {
      setInput('')
      setAttachments([])
    }

    if (useStream) {
      setStreaming(true)
      onRunStarted?.()
      let assistantContent = ''
      let composerCleared = false
      const clearComposerOnce = () => {
        if (composerCleared) return
        composerCleared = true
        setInput('')
        setAttachments([])
      }
      const control = streamChat(
        text,
        threadId ?? undefined,
        agentId,
        'user',
        lang,
        (envelope) => {
          clearComposerOnce()
          if (envelope.thread_id) onThreadId(envelope.thread_id)
          if (envelope.trace_id) onTraceUpdate(envelope.trace_id, envelope.run_id)

          const payload = envelope.data as Record<string, unknown> | null
          if (envelope.event === 'update' && payload?.data && typeof payload.data === 'object') {
            const streamData = payload.data as { type?: unknown; content?: unknown }
            if (streamData.type === 'message' && typeof streamData.content === 'string') {
              assistantContent += streamData.content
            }
          }

          if (envelope.event === 'command' && typeof payload?.response === 'string') {
            assistantContent = payload.response
          }
          if (envelope.event === 'interrupt' && payload) {
            const ref = payload.execution_ref as ExecutionRef | undefined
            if (ref?.interrupt_type === 'plan_confirm') {
              setPlanPending({
                executionRef: ref,
                todos: Array.isArray(payload.todos) ? payload.todos : [],
              })
            } else if (ref?.interrupt_type === 'tool_approval') {
              setApprovalPending(true)
              if (!assistantContent) assistantContent = '工具调用需要人工审批。'
            }
          }
          if (envelope.event === 'done') {
            const terminal = resolveStreamTerminalPayload(payload)
            if (!assistantContent && typeof terminal?.response === 'string') {
              assistantContent = terminal.response
            }
            const runMetrics = terminal?.run_metrics as RunMetricsSummary | undefined
            if (runMetrics && onRunMetrics) onRunMetrics(runMetrics)
            applyMemoryPayload(terminal)
          }

          if (assistantContent) {
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: assistantContent }
              } else {
                updated.push({ role: 'assistant', content: assistantContent })
              }
              return updated
            })
          }
        },
        () => {
          streamControlRef.current = null
          setLoading(false)
          setStreaming(false)
          clearComposerOnce()
        },
        (err) => {
          streamControlRef.current = null
          setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${err}` }])
          setLoading(false)
          setStreaming(false)
          setSendError(err)
        },
        requestExtras,
      )
      streamControlRef.current = control
      if (control?.threadId) {
        onThreadId(control.threadId)
      }
    } else {
      try {
        const result = await sendChat(text, threadId ?? undefined, agentId, 'user', lang, requestExtras)
        onThreadId(result.thread_id)
        if (result.trace_id) onTraceUpdate(result.trace_id, result.run_id)
        if (result.response) {
          setMessages(prev => [...prev, { role: 'assistant', content: result.response }])
        }
        if (result.interrupted && result.execution_ref?.interrupt_type === 'plan_confirm') {
          setPlanPending({ executionRef: result.execution_ref, todos: result.todos })
        } else if (result.interrupted && result.execution_ref?.interrupt_type === 'tool_approval') {
          setApprovalPending(true)
        }
        applyMemoryPayload(result as unknown as Record<string, unknown>)
        clearComposer()
      } catch (err) {
        setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${err}` }])
        setSendError(err instanceof Error ? err.message : String(err))
      } finally {
        setLoading(false)
      }
    }
  }

  const handleStop = async () => {
    const control = streamControlRef.current
    if (!control) return
    streamControlRef.current = null
    const result = await control.stop()
    setLoading(false)
    setStreaming(false)
    setMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        content: result.serverCancelled
          ? '已停止本地流读取；服务端已确认取消。'
          : `已停止本地流读取；服务端未确认取消：${result.detail}`,
      },
    ])
  }

  const handlePlanResolved = (response: string) => {
    setPlanPending(null)
    setMessages(prev => [...prev, { role: 'assistant', content: response }])
  }

  const copyMessage = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content)
    } catch {
      setSendError('复制失败，请检查浏览器权限。')
    }
  }

  const speakMessage = async (index: number, content: string) => {
    if (activeSpeechMessage === index && speechPlaybackState === 'playing') {
      setSpeechPlaybackState(speechControllerRef.current.pause())
      return
    }
    if (activeSpeechMessage === index && speechPlaybackState === 'paused') {
      setSpeechPlaybackState(speechControllerRef.current.resume())
      return
    }
    speechControllerRef.current.cancel()
    setActiveSpeechMessage(index)
    setVoiceOutputMode(speechControllerRef.current.mode)
    await speechControllerRef.current.speak(content)
    setVoiceOutputMode(speechControllerRef.current.mode)
  }

  const stopSpeechOutput = () => {
    setSpeechPlaybackState(speechControllerRef.current.stop())
    setActiveSpeechMessage(null)
    setPlaybackProgress({ current: 0, duration: 0 })
  }

  const downloadSpeech = async () => {
    const blob = await speechControllerRef.current.downloadBlob()
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = speechControllerRef.current.downloadFilename()
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const onDrop = async (event: React.DragEvent) => {
    event.preventDefault()
    composerRef.current?.classList.remove('drag-over')
    if (event.dataTransfer.files?.length) {
      await addFiles(event.dataTransfer.files)
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-thread-meta mono">
        {threadId ? (
          <>
            <span>THREAD {threadId.slice(0, 8)}</span>
            <span>·</span>
            <span>{streaming ? 'TRACE ACTIVE' : 'READY'}</span>
          </>
        ) : (
          <span>新对话 · 多模态 Agent 协作</span>
        )}
      </div>

      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={48} strokeWidth={1.5} />
            <h3>BoetClaw Agent 工作台</h3>
            <p>支持文档、图片、文件夹与语音输入的多模态协作空间</p>
            <div className="quick-prompts">
              {QUICK_PROMPTS.map(p => (
                <button key={p} type="button" className="quick-btn" onClick={() => setInput(p)}>{p}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={`${msg.role}-${i}`} className={`message ${msg.role}`}>
            <div className="message-avatar" aria-hidden>
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="message-body">
              {msg.role === 'assistant' && modelSelection && (
                <div className="message-meta mono">BOETCLAW · {modelSelection.model}</div>
              )}
              {msg.role === 'assistant' ? (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              ) : (
                <p>{msg.content}</p>
              )}
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="message-attachments">
                  {msg.attachments.map(item => (
                    <span key={`${item.filename}-${item.attachmentId ?? ''}`} className={`attachment-chip kind-${item.kind}`}>
                      {item.kind === 'image' ? '▣' : item.kind === 'text' ? '▧' : '▤'} {item.filename} · {item.sizeLabel}
                      {item.citation && <em className="attachment-citation"> · {item.citation}</em>}
                      {item.attachmentId && <span className="mono attachment-id"> · {item.attachmentId.slice(0, 8)}</span>}
                    </span>
                  ))}
                </div>
              )}
              {msg.role === 'assistant' && (
                <>
                  {activeSpeechMessage === i && speechPlaybackState !== 'idle' && speechPlaybackState !== 'unsupported' ? (
                    <MessageVoicePlayer
                      mode={voiceOutputMode}
                      state={speechPlaybackState}
                      progress={playbackProgress}
                      providerLabel={voiceCaps?.provider ?? null}
                      onTogglePlay={() => void speakMessage(i, msg.content)}
                      onStop={stopSpeechOutput}
                      onDownload={() => void downloadSpeech()}
                    />
                  ) : (
                    <div className="message-actions">
                      <button
                        type="button"
                        className="message-action-btn"
                        aria-label="朗读回复"
                        onClick={() => void speakMessage(i, msg.content)}
                      >
                        <Volume2 size={14} />
                        朗读
                      </button>
                      <button type="button" className="message-action-btn" aria-label="复制回复" onClick={() => void copyMessage(msg.content)}>
                        <Copy size={14} /> 复制
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        {loading && !streaming && (
          <div className="message assistant">
            <div className="message-avatar"><Loader2 size={18} className="spin" /></div>
            <div className="message-body"><p>处理中…</p></div>
          </div>
        )}
        {planPending && (
          <PlanConfirm
            key={planPending.executionRef.interrupt_id}
            executionRef={planPending.executionRef}
            todos={planPending.todos}
            onResolved={handlePlanResolved}
          />
        )}
        {approvalPending && <ApprovalCard />}
        {memoryCandidates.map(candidate => (
          <MemoryCandidateBar
            key={candidate.id}
            agentId={agentId}
            candidate={candidate}
            onResolved={() => {
              setMemoryCandidates(prev => prev.filter(item => item.id !== candidate.id))
              onMemoryContext?.(null)
            }}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <div
        ref={composerRef}
        className="chat-composer"
        onDragOver={e => { e.preventDefault(); composerRef.current?.classList.add('drag-over') }}
        onDragLeave={() => composerRef.current?.classList.remove('drag-over')}
        onDrop={e => void onDrop(e)}
      >
        <div className="composer-header">
          <span className="mono">附件队列 {attachments.length} / {ATTACHMENT_LIMITS.maxFiles}</span>
          <label className="stream-toggle">
            <input type="checkbox" checked={useStream} onChange={e => setUseStream(e.target.checked)} />
            流式输出
          </label>
        </div>

        {attachments.length > 0 && (
          <div className="attachment-queue" aria-label="附件队列">
            {attachments.map(item => (
              <div key={item.id} className={`attachment-card status-${item.status}`}>
                <div className="attachment-card-head mono">
                  {item.kind === 'image' ? 'IMG' : item.kind === 'text' ? 'TXT' : item.kind === 'document' ? 'DOC' : 'FILE'}
                </div>
                <div className="attachment-card-body">
                  <strong>{item.relativePath || item.file.name}</strong>
                  <span>{formatBytes(item.size)} · {item.statusMessage}</span>
                  {item.progress > 0 && item.progress < 100 && (
                    <span className="attachment-progress mono">上传 {item.progress}%</span>
                  )}
                </div>
                <div className="attachment-card-actions">
                  {item.status === 'failed' && (
                    <button type="button" className="attachment-action" onClick={() => void retryAttachment(item.id)}>重试</button>
                  )}
                  {['pending', 'uploading', 'parsing', 'uploaded'].includes(item.status) && (
                    <button type="button" className="attachment-action" onClick={() => void cancelAttachmentUpload(item.id)}>取消</button>
                  )}
                  <button type="button" className="attachment-remove" aria-label={`移除 ${item.file.name}`} onClick={() => removeAttachment(item.id)}>
                    <X size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {savedAttachments.length > 0 && (
          <div className="attachment-reuse" aria-label="可复用附件">
            <span className="mono">已上传可复用</span>
            {savedAttachments.slice(0, 6).map(record => (
              <button
                key={record.attachment_id}
                type="button"
                className="attachment-reuse-btn"
                onClick={() => reuseSavedAttachment(record)}
              >
                {record.filename}
              </button>
            ))}
          </div>
        )}

        {(speechState === 'recording' || speechState === 'listening' || speechState === 'preparing') && (
          <div className="voice-recording-bar" role="status" aria-live="polite">
            <div className="voice-recording-title">
              ● {voiceStatusLabel(speechState, voiceInputMode)} {formatSpeechDuration(speechSeconds)}
            </div>
            <div className="voice-recording-wave" aria-hidden>
              ▏▃▆█▅▂ ▂▅█▆▃▏ ▏▃▆█▅▂ ▂▅█▆▃▏
            </div>
            <div className="voice-recording-actions">
              {speechState === 'recording' && voiceInputMode === 'server' && (
                <button type="button" onClick={stopSpeechInput}>■ 停止并转写</button>
              )}
              {(speechState === 'listening' || speechState === 'recording') && (
                <button type="button" onClick={cancelSpeechInput}>× 取消</button>
              )}
              <span className="voice-recording-hint">
                {voiceInputMode === 'server'
                  ? '服务端高质量 · 音频不保存'
                  : '浏览器本地识别 · 不会自动发送'}
              </span>
            </div>
          </div>
        )}

        {(speechState === 'uploading' || speechState === 'transcribing') && (
          <div className="voice-recording-bar" role="status" aria-live="polite">
            <div className="voice-recording-title">{voiceStatusLabel(speechState, voiceInputMode)}</div>
            <div className="voice-recording-hint">可继续编辑文本，转写完成后将追加到输入框</div>
          </div>
        )}

        <div className="composer-input-wrap">
          <textarea
            value={speechPreview || input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend() } }}
            placeholder="输入消息，或点击麦克风说话…"
            rows={3}
            disabled={loading}
            aria-label="消息输入"
          />
          {speechState === 'listening' && voiceInputMode === 'browser' && (
            <div className="speech-live mono" role="status" aria-live="polite">
              ● 正在聆听 {formatSpeechDuration(speechSeconds)}
            </div>
          )}
          {lastVoiceInsert && (
            <button type="button" className="voice-undo-btn" onClick={undoVoiceInsert}>
              撤销本次语音插入
            </button>
          )}
        </div>

        {(attachmentError || sendError || visionBlocked || voiceError) && (
          <div className="composer-errors" role="alert">
            {attachmentError && <p>{attachmentError}</p>}
            {sendError && <p>{sendError}</p>}
            {voiceError && <p>{voiceError}</p>}
            {visionBlocked && <p>当前模型不支持图像输入，请切换模型或移除图片附件。</p>}
          </div>
        )}

        <div className="composer-toolbar">
          <div className="composer-tools">
            <input ref={fileInputRef} type="file" multiple hidden onChange={e => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
            <input ref={imageInputRef} type="file" accept="image/*" multiple hidden onChange={e => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
            <input ref={folderInputRef} type="file" {...({ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>)} multiple hidden onChange={e => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
            <button type="button" className="tool-btn" aria-label="添加文件" onClick={() => fileInputRef.current?.click()}>
              <Paperclip size={14} /> 文件
            </button>
            <button type="button" className="tool-btn" aria-label="添加图片" onClick={() => imageInputRef.current?.click()}>
              <ImagePlus size={14} /> 图片
            </button>
            <button type="button" className="tool-btn" aria-label="添加文件夹" onClick={() => folderInputRef.current?.click()}>
              <FolderOpen size={14} /> 文件夹
            </button>
            <button
              type="button"
              className={`tool-btn${['listening', 'recording', 'preparing'].includes(speechState) ? ' active' : ''}`}
              aria-label="语音输入"
              disabled={speechState === 'unsupported' || voiceInputBusy(speechState)}
              title={
                speechState === 'unsupported'
                  ? '当前浏览器不支持语音输入'
                  : speechState === 'permission-denied'
                    ? '麦克风权限被拒绝'
                    : voiceInputMode === 'server'
                      ? '服务端转写（不会自动发送）'
                      : '浏览器识别（不会自动发送）'
              }
              onClick={toggleSpeechInput}
            >
              {['listening', 'recording'].includes(speechState) ? <MicOff size={14} /> : <Mic size={14} />}
              语音
            </button>
          </div>
          <div className="composer-actions">
            <span className="composer-hint">支持拖放 · 单文件 ≤ 25 MB · Enter 发送</span>
            {streaming ? (
              <button type="button" className="send-btn stop-btn" onClick={() => void handleStop()} title="停止运行" aria-label="停止运行">
                <Square size={16} /> 停止
              </button>
            ) : (
              <button
                type="button"
                className="send-btn"
                onClick={() => void handleSend()}
                disabled={!canSend || visionBlocked}
                aria-label="发送消息"
              >
                {loading ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
                发送 ↵
              </button>
            )}
          </div>
        </div>
        {speechState === 'unsupported' && (
          <p className="composer-footnote" role="status">当前环境不支持语音输入；可在设置中查看语音能力状态。</p>
        )}
        {voiceCaps && voiceInputMode === 'browser' && voiceCaps.stt.status !== 'configured' && (
          <p className="composer-footnote" role="status">服务端转写未配置，当前使用浏览器本地识别。</p>
        )}
      </div>
    </div>
  )
}
