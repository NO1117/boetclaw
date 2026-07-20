import { useEffect, useState } from 'react'
import { Activity, Wrench, Radio } from 'lucide-react'
import { fetchRecentEvents, fetchTools, fetchStats, type TraceEvent, type ToolInfo, type Stats } from '../services/api'
import './SidePanel.css'

interface Props {
  activeTraceId: string | null
}

export default function SidePanel({ activeTraceId }: Props) {
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [tab, setTab] = useState<'trace' | 'tools' | 'stats'>('trace')

  useEffect(() => {
    const load = async () => {
      try {
        const [evts, toolData, st] = await Promise.all([
          fetchRecentEvents(30),
          fetchTools(),
          fetchStats(),
        ])
        setEvents(evts)
        setTools(toolData.tools)
        setStats(st)
      } catch { /* ignore */ }
    }
    load()
    const interval = setInterval(load, 3000)
    return () => clearInterval(interval)
  }, [activeTraceId])

  const filteredEvents = activeTraceId
    ? events.filter(e => e.trace_id === activeTraceId)
    : events

  const eventColor = (type: string) => {
    if (type.includes('guard') || type.includes('approval')) return 'var(--error)'
    if (type.includes('plan')) return 'var(--success)'
    if (type.includes('tool')) return 'var(--warning)'
    if (type.includes('subagent')) return '#a855f7'
    if (type.includes('agent') || type.includes('thinking')) return 'var(--accent)'
    if (type.includes('error')) return 'var(--error)'
    if (type.includes('gateway') || type.includes('cron') || type.includes('heartbeat')) return 'var(--info)'
    if (type.includes('skill') || type.includes('memory')) return 'var(--text-secondary)'
    return 'var(--text-muted)'
  }

  const eventCategory = (type: string): string => {
    if (type.includes('guard') || type.includes('approval')) return '安全'
    if (type.includes('plan')) return '规划'
    if (type.includes('tool')) return '工具'
    if (type.includes('subagent')) return '子智能体'
    if (type.includes('thinking') || type.includes('agent')) return '思考'
    if (type.includes('cron') || type.includes('heartbeat')) return '调度'
    if (type.includes('gateway')) return '网关'
    if (type.includes('skill')) return '技能'
    if (type.includes('memory')) return '记忆'
    return '其他'
  }

  return (
    <div className="side-panel">
      <div className="tab-bar">
        <button className={tab === 'trace' ? 'active' : ''} onClick={() => setTab('trace')}>
          <Activity size={14} /> 追踪
        </button>
        <button className={tab === 'tools' ? 'active' : ''} onClick={() => setTab('tools')}>
          <Wrench size={14} /> 工具
        </button>
        <button className={tab === 'stats' ? 'active' : ''} onClick={() => setTab('stats')}>
          <Radio size={14} /> 监控
        </button>
      </div>

      <div className="tab-content">
        {tab === 'trace' && (
          <div className="trace-list">
            {filteredEvents.length === 0 && (
              <div className="empty-state">暂无追踪事件</div>
            )}
            {filteredEvents.map(evt => (
              <div key={evt.id} className="trace-event">
                <div className="trace-dot" style={{ background: eventColor(evt.event_type) }} />
                <div className="trace-body">
                  <div className="trace-type">
                    <span
                      style={{
                        fontSize: 10,
                        padding: '1px 6px',
                        borderRadius: 8,
                        marginRight: 6,
                        background: eventColor(evt.event_type),
                        color: '#0a0e17',
                        fontWeight: 600,
                      }}
                    >
                      {eventCategory(evt.event_type)}
                    </span>
                    {evt.event_type}
                  </div>
                  <div className="trace-time">
                    {new Date(evt.timestamp).toLocaleTimeString('zh-CN')}
                  </div>
                  {Object.keys(evt.data).length > 0 && (
                    <pre className="trace-data">{JSON.stringify(evt.data, null, 2)}</pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'tools' && (
          <div className="tools-list">
            {tools.map(tool => (
              <div key={tool.name} className="tool-item">
                <div className="tool-name">{tool.name}</div>
                <div className="tool-desc">{tool.description}</div>
                <span className={`tool-source ${tool.source}`}>{tool.source}</span>
              </div>
            ))}
          </div>
        )}

        {tab === 'stats' && stats && (
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.trace_events}</div>
              <div className="stat-label">追踪事件</div>
            </div>
            {Object.entries(stats.tasks).map(([status, count]) => (
              <div key={status} className="stat-card">
                <div className="stat-value">{count}</div>
                <div className="stat-label">{status}</div>
              </div>
            ))}
            <div className="event-types">
              <h4>事件分布</h4>
              {Object.entries(stats.event_types).filter(([, c]) => c > 0).map(([type, count]) => (
                <div key={type} className="event-type-row">
                  <span>{type}</span>
                  <span className="count">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
