import { useCallback, useEffect, useState } from 'react'
import { Cpu, Plus, Star, Wifi, WifiOff } from 'lucide-react'
import VoiceCapabilityCard from './VoiceCapabilityCard'
import {
  checkProviderConnection,
  cloneProviderConnection,
  createProviderConnection,
  deleteProviderConnection,
  fetchProviderConnections,
  fetchConnectionModels,
  fetchVaultStatus,
  importEnvProviderCredentials,
  setDefaultProviderConnection,
  updateProviderConnection,
  type ProviderConnectionInfo,
  type ModelInfo,
  type VaultStatus,
} from '../services/api'

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  ollama: 'Ollama (本地)',
}

type DrawerMode = 'create' | 'edit' | null

function credentialLabel(conn: ProviderConnectionInfo): string {
  if (conn.provider_type === 'ollama') return '免密钥'
  if (!conn.credential_configured) return '未配置'
  const src = conn.credential_source === 'vault' ? '保险箱' : conn.credential_source === 'environment' ? '环境变量' : ''
  const fp = conn.credential_fingerprint ? ` ···${conn.credential_fingerprint}` : ''
  return `已配置${src ? ` (${src})` : ''}${fp}`
}

export default function ProviderSettings() {
  const [connections, setConnections] = useState<ProviderConnectionInfo[]>([])
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [checking, setChecking] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [importMsg, setImportMsg] = useState('')

  const [formProvider, setFormProvider] = useState('openai')
  const [formName, setFormName] = useState('')
  const [formBaseUrl, setFormBaseUrl] = useState('')
  const [formApiKey, setFormApiKey] = useState('')
  const [formModel, setFormModel] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [showApiKey, setShowApiKey] = useState(false)
  const [formRevision, setFormRevision] = useState<number | undefined>(undefined)

  const selected = connections.find(c => c.id === selectedId) ?? null

  const reload = useCallback(async () => {
    const [connResp, vault] = await Promise.all([
      fetchProviderConnections(),
      fetchVaultStatus(),
    ])
    setConnections(connResp.connections)
    setVaultStatus(vault)
  }, [])

  useEffect(() => {
    void reload().catch(() => { /* ignore */ })
  }, [reload])

  const resetForm = () => {
    setFormProvider('openai')
    setFormName('')
    setFormBaseUrl('')
    setFormApiKey('')
    setFormModel('')
    setFormEnabled(true)
    setFormRevision(undefined)
    setShowApiKey(false)
    setError('')
  }

  const openCreate = () => {
    resetForm()
    setDrawerMode('create')
    setSelectedId(null)
  }

  const openEdit = (conn: ProviderConnectionInfo) => {
    setSelectedId(conn.id)
    setDrawerMode('edit')
    setFormProvider(conn.provider_type)
    setFormName(conn.display_name)
    setFormBaseUrl(conn.base_url)
    setFormApiKey('')
    setFormModel(conn.default_model)
    setFormEnabled(conn.enabled)
    setFormRevision(conn.revision)
    setShowApiKey(false)
    setError('')
  }

  const closeDrawer = () => {
    setDrawerMode(null)
    setFormApiKey('')
    setShowApiKey(false)
  }

  const handleCheck = async (conn: ProviderConnectionInfo) => {
    setChecking(conn.id)
    setError('')
    try {
      await checkProviderConnection(conn.id)
      await reload()
    } catch (e) {
      setError(String(e))
    } finally {
      setChecking(null)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      if (drawerMode === 'create') {
        const payload = {
          provider_type: formProvider,
          display_name: formName,
          base_url: formBaseUrl,
          default_model: formModel,
          enabled: formEnabled,
          ...(formApiKey.trim() ? { api_key: formApiKey.trim() } : {}),
        }
        const res = await createProviderConnection(payload)
        if ('valid' in res) return
        const conn = res.connection
        setSuccess('连接已创建')
        closeDrawer()
        await reload()
        setSelectedId(conn.id)
      } else if (drawerMode === 'edit' && selectedId) {
        const payload = {
          display_name: formName,
          base_url: formBaseUrl,
          default_model: formModel,
          enabled: formEnabled,
          expected_revision: formRevision,
          ...(formApiKey.trim() ? { api_key: formApiKey.trim() } : {}),
        }
        await updateProviderConnection(selectedId, payload)
        setSuccess('连接已保存')
        setFormApiKey('')
        await reload()
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleSetDefault = async (conn: ProviderConnectionInfo) => {
    setSaving(true)
    setError('')
    try {
      await setDefaultProviderConnection(conn.id)
      setSuccess('已设为默认连接')
      await reload()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (conn: ProviderConnectionInfo) => {
    if (!window.confirm(`确定删除连接「${conn.display_name}」？`)) return
    setSaving(true)
    setError('')
    try {
      await deleteProviderConnection(conn.id)
      setSuccess('连接已删除')
      if (selectedId === conn.id) setSelectedId(null)
      await reload()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleClone = async (conn: ProviderConnectionInfo) => {
    setSaving(true)
    try {
      const res = await cloneProviderConnection(conn.id)
      setSuccess('已克隆连接')
      await reload()
      setSelectedId(res.connection.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleImportEnv = async () => {
    setImportMsg('')
    setError('')
    try {
      const res = await importEnvProviderCredentials()
      setImportMsg(res.message)
      await reload()
    } catch (e) {
      setError(String(e))
    }
  }

  const loadModels = async (conn: ProviderConnectionInfo) => {
    setSelectedId(conn.id)
    try {
      const data = await fetchConnectionModels(conn.id)
      setModels(data.models)
    } catch {
      setModels([])
    }
  }

  return (
    <div>
      <div className="mgr-section-title">模型连接</div>
      {vaultStatus && !vaultStatus.writable && (
        <p style={{ fontSize: 12, color: 'var(--warning, #b45309)', marginBottom: 8 }}>
          {vaultStatus.message || '保险箱写入已禁用；可继续使用环境变量凭据。'}
        </p>
      )}
      <div className="mgr-actions" style={{ marginBottom: 8 }}>
        <button className="mgr-btn" type="button" onClick={() => openCreate()}>
          <Plus size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          新建连接
        </button>
        <button className="mgr-btn secondary" type="button" onClick={() => void handleImportEnv()}>
          从环境变量导入
        </button>
      </div>
      {importMsg && <p style={{ fontSize: 12, marginBottom: 8 }}>{importMsg}</p>}
      {success && <p style={{ fontSize: 12, color: 'var(--success, #059669)' }}>{success}</p>}
      {error && <p style={{ fontSize: 12, color: 'var(--error)' }}>{error}</p>}

      <div className="mgr-list">
        {connections.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>暂无连接；可新建或从环境变量导入。</p>
        )}
        {connections.map(conn => (
          <div className="mgr-item" key={conn.id}>
            <div className="mgr-item-main">
              <h4>
                <Cpu size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                {conn.display_name}
                {conn.is_default && (
                  <Star size={11} style={{ marginLeft: 4, verticalAlign: 'middle' }} aria-label="默认连接" />
                )}
              </h4>
              <p>
                {PROVIDER_LABELS[conn.provider_type] ?? conn.provider_type}
                {' · '}
                {conn.base_url || '默认端点'}
                {' · '}
                {credentialLabel(conn)}
                {' · '}
                模型 {conn.default_model || '—'}
              </p>
              {conn.last_check && (
                <p style={{ fontSize: 11 }}>
                  最近检测：{conn.last_check.connected ? '连通' : '失败'}
                  {conn.last_check.latency_ms ? ` · ${conn.last_check.latency_ms}ms` : ''}
                  {conn.last_check.model_count ? ` · ${conn.last_check.model_count} 模型` : ''}
                </p>
              )}
            </div>
            <div className="mgr-actions">
              <span className={`pill ${conn.enabled ? 'ok' : 'off'}`}>{conn.enabled ? '启用' : '停用'}</span>
              {conn.last_check && (
                <span className={`pill ${conn.last_check.connected ? 'ok' : 'off'}`}>
                  {conn.last_check.connected ? <Wifi size={11} /> : <WifiOff size={11} />}
                </span>
              )}
              <button className="mgr-btn secondary" disabled={checking === conn.id} onClick={() => void handleCheck(conn)}>
                检测
              </button>
              <button className="mgr-btn secondary" onClick={() => void loadModels(conn)}>模型</button>
              <button className="mgr-btn secondary" onClick={() => openEdit(conn)}>编辑</button>
              {!conn.is_default && (
                <button className="mgr-btn secondary" disabled={saving} onClick={() => void handleSetDefault(conn)}>
                  设为默认
                </button>
              )}
              <button className="mgr-btn secondary" disabled={saving} onClick={() => void handleClone(conn)}>克隆</button>
              <button className="mgr-btn secondary" disabled={saving} onClick={() => void handleDelete(conn)}>删除</button>
            </div>
          </div>
        ))}
      </div>

      {drawerMode && (
        <>
          <div className="mgr-section-title">{drawerMode === 'create' ? '新建连接' : '编辑连接'}</div>
          <div className="mgr-form">
            {drawerMode === 'create' && (
              <label>
                Provider
                <select value={formProvider} onChange={e => setFormProvider(e.target.value)}>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="ollama">Ollama</option>
                </select>
              </label>
            )}
            <input placeholder="显示名称" value={formName} onChange={e => setFormName(e.target.value)} />
            <input
              placeholder="Base URL（可选）"
              value={formBaseUrl}
              onChange={e => setFormBaseUrl(e.target.value)}
            />
            {formProvider !== 'ollama' && (
              <>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    placeholder={
                      drawerMode === 'edit' && selected?.credential_configured
                        ? 'API Key 已配置；输入新值以替换'
                        : 'API Key'
                    }
                    type={showApiKey ? 'text' : 'password'}
                    value={formApiKey}
                    onChange={e => setFormApiKey(e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button type="button" className="mgr-btn secondary" onClick={() => setShowApiKey(v => !v)}>
                    {showApiKey ? '隐藏' : '显示'}
                  </button>
                </div>
                {drawerMode === 'edit' && selected && (
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>{credentialLabel(selected)}</span>
                )}
              </>
            )}
            <input
              placeholder="默认模型"
              value={formModel}
              onChange={e => setFormModel(e.target.value)}
            />
            <label style={{ fontSize: 12 }}>
              <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)} />
              {' '}启用此连接
            </label>
            <div className="mgr-actions">
              <button className="mgr-btn" disabled={saving} onClick={() => void handleSave()}>保存</button>
              <button className="mgr-btn secondary" onClick={closeDrawer}>取消</button>
            </div>
          </div>
        </>
      )}

      {selected && models.length > 0 && (
        <>
          <div className="mgr-section-title">{selected.display_name} · 可用模型</div>
          <div className="mgr-list">
            {models.map(m => (
              <div className="mgr-item" key={m.name}>
                <div className="mgr-item-main">
                  <h4>{m.name}</h4>
                  <p>上下文 {m.context_window || '—'}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <VoiceCapabilityCard />
    </div>
  )
}
