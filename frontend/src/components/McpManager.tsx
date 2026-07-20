import { useEffect, useState } from 'react'
import { RefreshCw, Server, Wrench } from 'lucide-react'
import {
  fetchMcpServers,
  fetchMcpTools,
  reloadMcp,
  type McpReloadResult,
  type McpServerStatus,
  type McpToolDetail,
} from '../services/api'

export default function McpManager() {
  const [servers, setServers] = useState<McpServerStatus[]>([])
  const [tools, setTools] = useState<McpToolDetail[]>([])
  const [selected, setSelected] = useState<McpToolDetail | null>(null)
  const [lastReload, setLastReload] = useState<McpReloadResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const [serverData, toolData] = await Promise.all([fetchMcpServers(), fetchMcpTools()])
      setServers(serverData.servers)
      setTools(toolData.tools)
    } catch (e) {
      setError(String(e))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleReload = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await reloadMcp()
      setLastReload(result)
      setServers(result.servers)
      setTools(result.mcp_tool_details)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mgr-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>MCP Server 状态</span>
        <div className="mgr-actions">
          <button className="mgr-btn secondary" onClick={() => void load()} disabled={busy}>
            <RefreshCw size={12} /> 刷新
          </button>
          <button className="mgr-btn" onClick={() => void handleReload()} disabled={busy}>
            Reload MCP
          </button>
        </div>
      </div>
      {error && <div className="detail-action-error">{error}</div>}
      {lastReload && (
        <div className="security-hint">
          最近 reload：{lastReload.status}，总工具 {lastReload.tools}，MCP 工具 {lastReload.mcp_tools}
        </div>
      )}

      <div className="mgr-list">
        {servers.length === 0 && <div className="empty-hint">暂无 MCP server 配置。</div>}
        {servers.map(server => (
          <div className="mgr-item" key={server.name}>
            <div className="mgr-item-main">
              <h4><Server size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{server.name}</h4>
              <p>{JSON.stringify(server.config)}</p>
            </div>
            <div className="mgr-actions">
              <span className={`pill ${server.configured ? 'ok' : 'off'}`}>{server.configured ? '已配置' : '未配置'}</span>
              <span className={`pill ${server.connected ? 'ok' : 'off'}`}>{server.connected ? '已连接' : '未连接'}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mgr-section-title">MCP 工具详情</div>
      <div className="mcp-tool-grid">
        <div className="mgr-list">
          {tools.length === 0 && <div className="empty-hint">暂无 MCP 工具。</div>}
          {tools.map(tool => (
            <button
              key={tool.name}
              className={`route-list-item ${selected?.name === tool.name ? 'active' : ''}`}
              onClick={() => setSelected(tool)}
            >
              <div>
                <strong><Wrench size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{tool.name}</strong>
                <p>{tool.description || '—'}</p>
              </div>
            </button>
          ))}
        </div>
        <div className="route-card task-detail-card">
          {!selected && <div className="empty-hint">选择一个 MCP 工具查看参数 schema。</div>}
          {selected && (
            <>
              <h3>{selected.name}</h3>
              <div className="detail-section">
                <label>Description</label>
                <pre>{selected.description || '—'}</pre>
              </div>
              <div className="detail-section">
                <label>Args Schema</label>
                <pre>{JSON.stringify(selected.args_schema, null, 2)}</pre>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
