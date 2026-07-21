import { useEffect, useState } from 'react'
import { Cpu, Wifi, WifiOff } from 'lucide-react'
import {
  fetchProviders,
  fetchDefaultProviderConfig,
  fetchProviderConfig,
  fetchProviderModels,
  checkProvider,
  updateDefaultProvider,
  updateProviderConfig,
  type ProviderInfo,
  type ModelInfo,
  type ProviderConfig,
  type DefaultProviderConfig,
} from '../services/api'

export default function ProviderSettings() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({})
  const [conn, setConn] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<string>('')
  const [defaultCfg, setDefaultCfg] = useState<DefaultProviderConfig | null>(null)
  const [providerCfg, setProviderCfg] = useState<ProviderConfig | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [defaultModel, setDefaultModel] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const [data, def] = await Promise.all([fetchProviders(), fetchDefaultProviderConfig()])
        setProviders(data.providers)
        setDefaultCfg(def)
        if (data.providers.length > 0) setSelected(data.providers[0].name)
      } catch { /* ignore */ }
    })()
  }, [])

  useEffect(() => {
    if (!selected) return
    void loadConfig(selected)
  }, [selected])

  const loadConfig = async (name: string) => {
    try {
      const cfg = await fetchProviderConfig(name)
      setProviderCfg(cfg)
      setApiKey('')
      setBaseUrl(cfg.base_url || '')
      setDefaultModel(defaultCfg?.provider === name ? defaultCfg.model : cfg.default_model)
    } catch (e) {
      setError(String(e))
    }
  }

  const loadModels = async (name: string) => {
    setSelected(name)
    if (!models[name]) {
      try {
        const data = await fetchProviderModels(name)
        setModels(prev => ({ ...prev, [name]: data.models }))
      } catch { /* ignore */ }
    }
  }

  const reloadProviders = async () => {
    const [data, def] = await Promise.all([fetchProviders(), fetchDefaultProviderConfig()])
    setProviders(data.providers)
    setDefaultCfg(def)
  }

  const handleCheck = async (name: string) => {
    try {
      const res = await checkProvider(name)
      setConn(prev => ({ ...prev, [name]: res.connected }))
    } catch {
      setConn(prev => ({ ...prev, [name]: false }))
    }
  }

  const handleSaveConfig = async () => {
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      const payload: { api_key?: string; base_url?: string } = { base_url: baseUrl }
      if (apiKey.trim()) payload.api_key = apiKey.trim()
      const cfg = await updateProviderConfig(selected, payload)
      setProviderCfg(cfg)
      setApiKey('')
      await reloadProviders()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleSetDefault = async () => {
    if (!selected || !defaultModel.trim()) return
    setSaving(true)
    setError('')
    try {
      const cfg = await updateDefaultProvider(selected, defaultModel.trim())
      setDefaultCfg(cfg)
      await loadConfig(selected)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="mgr-section-title">模型提供商</div>
      <div className="mgr-list">
        {providers.map(p => (
          <div className="mgr-item" key={p.name}>
            <div className="mgr-item-main">
              <h4>
                <Cpu size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                {p.display_name}
              </h4>
              <p>默认模型：{p.default_model} · {p.requires_api_key ? '需要 API Key' : '本地/免密钥'}</p>
            </div>
            <div className="mgr-actions">
              <span className={`pill ${p.configured ? 'ok' : 'off'}`}>{p.configured ? '已配置' : '未配置'}</span>
              {conn[p.name] !== undefined && (
                <span className={`pill ${conn[p.name] ? 'ok' : 'off'}`}>
                  {conn[p.name] ? <Wifi size={11} /> : <WifiOff size={11} />}
                  {conn[p.name] ? ' 连通' : ' 不通'}
                </span>
              )}
              <button className="mgr-btn secondary" onClick={() => void handleCheck(p.name)}>检测</button>
              <button className="mgr-btn secondary" onClick={() => void loadModels(p.name)}>模型</button>
              <button className="mgr-btn secondary" onClick={() => setSelected(p.name)}>配置</button>
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <>
          <div className="mgr-section-title">{selected} · 运行期配置</div>
          <div className="mgr-form">
            <input
              placeholder={providerCfg?.api_key_configured ? 'API Key 已配置；留空不修改' : 'API Key（可选）'}
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              disabled={selected === 'ollama'}
            />
            <input
              placeholder="Base URL，如 http://localhost:11434 或 http://localhost:8001/v1"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
            />
            <input
              placeholder="默认模型，如 gpt-4o / qwen2.5"
              value={defaultModel}
              onChange={e => setDefaultModel(e.target.value)}
            />
            {error && <span style={{ color: 'var(--error)', fontSize: 12 }}>{error}</span>}
            <div className="mgr-actions">
              <button className="mgr-btn" disabled={saving} onClick={() => void handleSaveConfig()}>保存配置</button>
              <button className="mgr-btn secondary" disabled={saving || !defaultModel.trim()} onClick={() => void handleSetDefault()}>
                设为默认模型
              </button>
              {defaultCfg?.provider === selected && (
                <span className="pill ok">当前默认：{defaultCfg.model}</span>
              )}
            </div>
          </div>
        </>
      )}

      {selected && models[selected] && (
        <>
          <div className="mgr-section-title">{selected} · 可用模型</div>
          <div className="mgr-list">
            {models[selected].map(m => (
              <div className="mgr-item" key={m.name}>
                <div className="mgr-item-main">
                  <h4>{m.name}</h4>
                  <p>
                    上下文 {m.context_window || '—'} · 工具 {m.supports_tools ? '✓' : '✗'} · 视觉{' '}
                    {m.supports_vision === true ? '✓' : m.supports_vision === false ? '✗' : '?'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
