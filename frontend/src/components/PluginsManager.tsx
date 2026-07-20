import { useEffect, useState } from 'react'
import { Puzzle, RefreshCw, ShieldAlert, ShieldCheck, Trash2 } from 'lucide-react'
import {
  deletePlugin,
  fetchPluginDetail,
  fetchPluginScanReport,
  fetchPlugins,
  installPlugin,
  reloadPlugins,
  setPluginEnabled,
  type PluginDetail,
  type PluginInfo,
  type PluginScanFinding,
} from '../services/api'

export default function PluginsManager() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<PluginDetail | null>(null)
  const [findings, setFindings] = useState<PluginScanFinding[]>([])
  const [scanSafe, setScanSafe] = useState<boolean | null>(null)
  const [installName, setInstallName] = useState('')
  const [sourceDir, setSourceDir] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const data = await fetchPlugins()
      setPlugins(data.plugins)
    } catch (e) { setError(String(e)) }
  }

  useEffect(() => { void load() }, [])

  const handleReload = async () => {
    setBusy(true)
    try {
      await reloadPlugins()
      await load()
    } catch (e) { setError(String(e)) }
    setBusy(false)
  }

  const handleInstall = async () => {
    if (!installName.trim() || !sourceDir.trim()) return
    setBusy(true)
    setError('')
    try {
      await installPlugin(installName.trim(), sourceDir.trim(), overwrite)
      setInstallName('')
      setSourceDir('')
      setOverwrite(false)
      await load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleToggle = async (plugin: PluginInfo) => {
    setBusy(true)
    setError('')
    try {
      const updated = await setPluginEnabled(plugin.name, !plugin.enabled)
      setPlugins(prev => prev.map(p => p.name === updated.name ? updated : p))
      if (selected?.name === updated.name) {
        setSelected(await fetchPluginDetail(updated.name))
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleDetail = async (name: string) => {
    setError('')
    try {
      const detail = await fetchPluginDetail(name)
      setSelected(detail)
      setFindings(detail.scan?.findings ?? [])
      setScanSafe(detail.scan?.safe ?? null)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleScanReport = async (name: string) => {
    setError('')
    try {
      const report = await fetchPluginScanReport(name)
      setFindings(report.findings)
      setScanSafe(report.safe)
      if (selected?.name !== name) {
        setSelected(await fetchPluginDetail(name))
      }
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (name: string) => {
    if (!window.confirm(`确认删除插件 ${name}？将移除目录并从 ENABLED_PLUGINS 清除。`)) return
    setBusy(true)
    setError('')
    try {
      await deletePlugin(name)
      if (selected?.name === name) {
        setSelected(null)
        setFindings([])
        setScanSafe(null)
      }
      await load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mgr-section-title">安装插件</div>
      <div className="mgr-form plugin-install-form">
        <input placeholder="插件名称（需与 manifest.name 一致）" value={installName} onChange={e => setInstallName(e.target.value)} />
        <input placeholder="源目录（包含 manifest.json）" value={sourceDir} onChange={e => setSourceDir(e.target.value)} />
        <label className="inline-check">
          <input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} />
          覆盖已存在
        </label>
        <button className="mgr-btn" disabled={busy} onClick={() => void handleInstall()}>安装</button>
      </div>
      {error && <div className="detail-action-error">{error}</div>}

      <div className="mgr-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>已发现插件</span>
        <button className="mgr-btn secondary" onClick={() => void handleReload()} disabled={busy}>
          <RefreshCw size={12} /> 重新加载
        </button>
      </div>
      <div className="mgr-list">
        {plugins.length === 0 && <div className="empty-hint">plugins_ext/ 下暂无插件。默认安全策略：未在 ENABLED_PLUGINS 中的插件不会加载。</div>}
        {plugins.map(p => (
          <div className="mgr-item" key={p.name}>
            <div className="mgr-item-main">
              <h4><Puzzle size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{p.name} <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>v{p.version} · {p.type}</span></h4>
              <p>{p.description || '—'}{p.tools.length > 0 ? ` · 工具: ${p.tools.join(', ')}` : ''}{p.error ? ` · 错误: ${p.error}` : ''}</p>
              <p>{p.path}</p>
            </div>
            <div className="mgr-actions">
              <span className={`pill ${p.enabled ? 'ok' : 'off'}`}>{p.enabled ? '已启用' : '未启用'}</span>
              <span className={`pill ${p.loaded ? 'ok' : 'off'}`}>{p.loaded ? '已加载' : '未加载'}</span>
              {p.error && <span className="pill off"><ShieldAlert size={11} /> 错误隔离</span>}
              <button className="mgr-btn secondary" onClick={() => void handleDetail(p.name)}>详情</button>
              <button className="mgr-btn secondary" onClick={() => void handleScanReport(p.name)}>扫描报告</button>
              <button className={`mgr-btn ${p.enabled ? 'danger' : ''}`} disabled={busy} onClick={() => void handleToggle(p)}>
                {p.enabled ? '停用' : '启用'}
              </button>
              <button className="mgr-btn danger" disabled={busy} onClick={() => void handleDelete(p.name)}>
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <>
          <div className="mgr-section-title">{selected.name} · manifest 详情</div>
          <div className="route-card task-detail-card">
            <div className="detail-meta">
              <span className={`pill ${selected.enabled ? 'ok' : 'off'}`}>{selected.enabled ? 'enabled' : 'disabled'}</span>
              <span className={`pill ${selected.loaded ? 'ok' : 'off'}`}>{selected.loaded ? 'loaded' : 'not loaded'}</span>
              {scanSafe !== null && (
                <span className={`pill ${scanSafe ? 'ok' : 'off'}`}>
                  {scanSafe ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                  {scanSafe ? ' 扫描安全' : ' 扫描风险'}
                </span>
              )}
              <span>{selected.path}</span>
            </div>
            {selected.error && (
              <div className="detail-section error">
                <label>Load Error</label>
                <pre>{selected.error}</pre>
              </div>
            )}
            <div className="detail-section">
              <label>Tools</label>
              <pre>{selected.tools.length > 0 ? selected.tools.join('\n') : '—'}</pre>
            </div>
            <div className="detail-section">
              <label>Manifest</label>
              <pre>{JSON.stringify(selected.manifest, null, 2)}</pre>
            </div>
            <div className="detail-section">
              <label>Scan Report</label>
              <pre>
                {findings.length === 0
                  ? (scanSafe === false ? '（无 findings，但标记不安全）' : '无风险项')
                  : findings.map(f => `${f.file}:${f.line} [${f.category}] ${f.snippet}`).join('\n')}
              </pre>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
