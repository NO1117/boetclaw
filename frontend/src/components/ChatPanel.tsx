import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Send, Loader2, Bot, User, Square } from 'lucide-react'
import {
  sendChat,
  streamChat,
  type ChatMessage,
  type ExecutionRef,
  type StreamControl,
} from '../services/api'
import PlanConfirm from './PlanConfirm'
import ApprovalCard from './ApprovalCard'
import './ChatPanel.css'

interface Props {
  threadId: string | null
  agentId: string
  onThreadId: (id: string) => void
  onTraceUpdate: (traceId: string, runId: string) => void
  initialMessages?: ChatMessage[]
  historyVersion?: number
}

interface PlanPending {
  executionRef: ExecutionRef
  todos: unknown[]
}

export default function ChatPanel({
  threadId,
  agentId,
  onThreadId,
  onTraceUpdate,
  initialMessages = [],
  historyVersion = 0,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [useStream, setUseStream] = useState(true)
  const [planPending, setPlanPending] = useState<PlanPending | null>(null)
  const [approvalPending, setApprovalPending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const streamControlRef = useRef<StreamControl | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setMessages(initialMessages)
  }, [historyVersion])

  useEffect(() => () => {
    if (streamControlRef.current) void streamControlRef.current.stop()
  }, [])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    const lang = navigator.language
    if (useStream) {
      setStreaming(true)
      let assistantContent = ''
      const control = streamChat(
        text,
        threadId ?? undefined,
        agentId,
        'user',
        lang,
        (envelope) => {
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
          if (envelope.event === 'done' && !assistantContent && typeof payload?.response === 'string') {
            assistantContent = payload.response
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
        },
        (err) => {
          streamControlRef.current = null
          setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${err}` }])
          setLoading(false)
          setStreaming(false)
        },
      )
      streamControlRef.current = control
      onThreadId(control.threadId)
    } else {
      try {
        const result = await sendChat(text, threadId ?? undefined, agentId, 'user', lang)
        onThreadId(result.thread_id)
        if (result.trace_id) onTraceUpdate(result.trace_id, result.run_id)
        if (result.response) {
          setMessages(prev => [...prev, { role: 'assistant', content: result.response }])
        }
        if (
          result.interrupted
          && result.execution_ref?.interrupt_type === 'plan_confirm'
        ) {
          setPlanPending({ executionRef: result.execution_ref, todos: result.todos })
        } else if (
          result.interrupted
          && result.execution_ref?.interrupt_type === 'tool_approval'
        ) {
          setApprovalPending(true)
        }
      } catch (err) {
        setMessages(prev => [...prev, { role: 'assistant', content: `错误: ${err}` }])
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

  const quickPrompts = [
    '审查这份钻井日报的完整性',
    '生成 XX-1 井钻井日报模板',
    '绘制 WOB/RPM 随井深变化曲线',
    '编写 LAS 文件解析 Python 脚本',
  ]

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h2>智能对话</h2>
        <label className="stream-toggle">
          <input type="checkbox" checked={useStream} onChange={e => setUseStream(e.target.checked)} />
          流式输出
        </label>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={48} strokeWidth={1.5} />
            <h3>BoetClaw 钻井智能体</h3>
            <p>支持文本审查、文档生成、图表绘制、代码编写等复杂任务</p>
            <div className="quick-prompts">
              {quickPrompts.map(p => (
                <button key={p} className="quick-btn" onClick={() => setInput(p)}>{p}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="message-body">
              {msg.role === 'assistant' ? (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              ) : (
                <p>{msg.content}</p>
              )}
            </div>
          </div>
        ))}
        {loading && !streaming && (
          <div className="message assistant">
            <div className="message-avatar"><Loader2 size={18} className="spin" /></div>
            <div className="message-body"><p>处理中...</p></div>
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
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          placeholder="输入任务描述，如：审查钻井报告、生成图表..."
          rows={2}
          disabled={loading}
        />
        {streaming ? (
          <button className="send-btn stop-btn" onClick={handleStop} title="停止运行">
            <Square size={18} />
          </button>
        ) : (
          <button className="send-btn" onClick={handleSend} disabled={loading || !input.trim()}>
            {loading ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
          </button>
        )}
      </div>
    </div>
  )
}
