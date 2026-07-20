import { useEffect, useState } from 'react'
import { RefreshCw, Radio } from 'lucide-react'
import {
  fetchGatewayAccessControl,
  fetchGatewayMessages,
  fetchGatewayStatus,
  retryGatewayMessage,
  updateGatewayAccessControl,
  type GatewayAccessControl,
  type GatewayChannelStatus,
  type GatewayMessageRecord,
} from '../services/api'

export default function ChannelsManager() {
  const [channels, setChannels] = useState<GatewayChannelStatus[]>([])
  const [messages, setMessages] = useState<GatewayMessageRecord[]>([])
  const [platform, setPlatform] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [accessDraft, setAccessDraft] = useState<Record<string, string>>({})

  const parseUsers = (value: string) => value
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean)

  const buildAccessPayload = (): GatewayAccessControl => ({
    channels: Object.fromEntries(
      channels.map(ch => [ch.name, { allowed_users: parseUsers(accessDraft[ch.name] || '') }]),
    ),
  })

  const load = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const [statusData, messageData, accessData] = await Promise.all([
        fetchGatewayStatus(),
        fetchGatewayMessages(platform, status, 100),
        fetchGatewayAccessControl(),
      ])
      setChannels(statusData.channels)
      setMessages(messageData.messages)
      setAccessDraft(Object.fromEntries(
        statusData.channels.map(ch => [
          ch.name,
          (accessData.channels[ch.name]?.allowed_users || []).join('\n'),
        ]),
      ))
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleRetry = async (id: string) => {
    setError('')
    try {
      await retryGatewayMessage(id)
      await load()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleSaveAccess = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await updateGatewayAccessControl(buildAccessPayload())
      setAccessDraft(Object.fromEntries(
        channels.map(ch => [ch.name, (saved.channels[ch.name]?.allowed_users || []).join('\n')]),
      ))
      setNotice('渠道访问白名单已保存。')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mgr-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>渠道配置状态与队列</span>
        <button className="mgr-btn secondary" onClick={() => void load()} disabled={busy}>
          <RefreshCw size={12} /> 刷新
        </button>
      </div>
      {error && <div className="detail-action-error">{error}</div>}
      {notice && <div className="empty-hint">{notice}</div>}
      <div className="stats-grid channel-stats-grid">
        {channels.map(ch => (
          <div className="stat-card" key={ch.name}>
            <div className="stat-value">{ch.queue_depth}</div>
            <div className="stat-label">{ch.name} queue</div>
            <div className="channel-status-line">
              <span className={`pill ${ch.configured ? 'ok' : 'off'}`}>{ch.configured ? 'configured' : 'not configured'}</span>
              <span className={`pill ${ch.consumer_running ? 'ok' : 'off'}`}>{ch.consumer_running ? 'consumer' : 'idle'}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mgr-section-title">渠道访问白名单</div>
      <div className="route-card channel-access-card">
        <p className="empty-hint">每行或逗号分隔一个 user_id。留空表示该渠道开放；填写后仅白名单用户可触发任务。</p>
        <div className="channel-access-grid">
          {channels.map(ch => (
            <label className="channel-access-item" key={ch.name}>
              <span>{ch.name}</span>
              <textarea
                rows={3}
                placeholder="u_123&#10;u_456"
                value={accessDraft[ch.name] || ''}
                onChange={e => setAccessDraft(prev => ({ ...prev, [ch.name]: e.target.value }))}
              />
            </label>
          ))}
        </div>
        <button className="mgr-btn" onClick={() => void handleSaveAccess()} disabled={busy || channels.length === 0}>
          保存白名单
        </button>
      </div>

      <div className="mgr-section-title">消息历史、失败重试与回发记录</div>
      <div className="mgr-form gateway-filter-form">
        <input placeholder="平台过滤，如 feishu" value={platform} onChange={e => setPlatform(e.target.value)} />
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          <option value="queued">queued</option>
          <option value="denied">denied</option>
          <option value="replied">replied</option>
          <option value="failed">failed</option>
        </select>
        <button className="mgr-btn secondary" onClick={() => void load()}>筛选</button>
      </div>
      <div className="mgr-list">
        {messages.length === 0 && <div className="empty-hint">暂无渠道消息记录。</div>}
        {messages.map(msg => (
          <div className="mgr-item" key={msg.id}>
            <div className="mgr-item-main">
              <h4><Radio size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{msg.platform} · {msg.status}</h4>
              <p>{msg.content || '—'}</p>
              <p>
                chat {msg.chat_id || '—'} · message {msg.message_id || '—'} · task {msg.task_id || '—'} · trace {msg.trace_id || '—'}
              </p>
              <p>{msg.detail || '—'} · {new Date(msg.created_at).toLocaleString('zh-CN')}</p>
            </div>
            <div className="mgr-actions">
              <span className={`pill ${msg.status === 'replied' ? 'ok' : msg.status === 'failed' ? 'off' : ''}`}>{msg.status}</span>
              {msg.status === 'failed' && (
                <button className="mgr-btn secondary" onClick={() => void handleRetry(msg.id)}>重试</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
