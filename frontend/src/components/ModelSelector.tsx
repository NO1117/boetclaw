import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Eye, EyeOff, Loader2 } from 'lucide-react'
import {
  fetchDefaultProviderConfig,
  fetchProviderModels,
  fetchProviders,
  type ModelInfo,
  type ProviderInfo,
} from '../services/api'

export interface ModelSelection {
  provider: string
  model: string
  supportsVision: boolean
  label: string
}

interface ModelSelectorProps {
  value: ModelSelection | null
  onChange: (selection: ModelSelection | null) => void
  disabled?: boolean
}

function buildLabel(provider: string, model: string): string {
  return `${provider} / ${model}`
}

export default function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelInfo[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const [providerResp, defaultCfg] = await Promise.all([
          fetchProviders(),
          fetchDefaultProviderConfig(),
        ])
        if (cancelled) return
        const configured = providerResp.providers.filter(p => p.configured)
        setProviders(configured)
        const modelMap: Record<string, ModelInfo[]> = {}
        await Promise.all(
          configured.map(async provider => {
            try {
              const resp = await fetchProviderModels(provider.name)
              modelMap[provider.name] = resp.models
            } catch {
              modelMap[provider.name] = []
            }
          }),
        )
        if (cancelled) return
        setModelsByProvider(modelMap)
        if (!value) {
          const provider = configured.find(p => p.name === defaultCfg.provider) ?? configured[0]
          const models = modelMap[provider?.name ?? ''] ?? []
          const model = models.find(m => m.name === defaultCfg.model)?.name
            ?? provider?.default_model
            ?? models[0]?.name
          if (provider && model) {
            onChange({
              provider: provider.name,
              model,
              supportsVision: models.find(m => m.name === model)?.supports_vision ?? false,
              label: buildLabel(provider.display_name || provider.name, model),
            })
          }
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  const currentModels = useMemo(
    () => (value ? modelsByProvider[value.provider] ?? [] : []),
    [modelsByProvider, value],
  )

  const handleProviderChange = (providerName: string) => {
    const models = modelsByProvider[providerName] ?? []
    const provider = providers.find(p => p.name === providerName)
    const model = models[0]?.name ?? provider?.default_model ?? ''
    if (!model) return
    onChange({
      provider: providerName,
      model,
      supportsVision: models[0]?.supports_vision ?? false,
      label: buildLabel(provider?.display_name || providerName, model),
    })
  }

  const handleModelChange = (modelName: string) => {
    if (!value) return
    const model = currentModels.find(m => m.name === modelName)
    const provider = providers.find(p => p.name === value.provider)
    onChange({
      provider: value.provider,
      model: modelName,
      supportsVision: model?.supports_vision ?? false,
      label: buildLabel(provider?.display_name || value.provider, modelName),
    })
  }

  if (loading) {
    return (
      <div className="model-selector loading" aria-busy="true">
        <Loader2 size={14} className="spin" aria-hidden />
        <span>加载模型…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="model-selector error" role="alert">
        <span>模型加载失败</span>
      </div>
    )
  }

  if (!value || providers.length === 0) {
    return (
      <div className="model-selector disabled" title="无可用 Provider">
        未配置模型
      </div>
    )
  }

  return (
    <div className={`model-selector${open ? ' open' : ''}`}>
      <button
        type="button"
        className="model-selector-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="选择模型"
        disabled={disabled}
        onClick={() => setOpen(v => !v)}
      >
        <span className="mono">{value.label}</span>
        {value.supportsVision ? <Eye size={14} aria-label="支持视觉" /> : <EyeOff size={14} aria-label="不支持视觉" />}
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="model-selector-menu" role="listbox" aria-label="Provider 与模型">
          <label className="model-selector-field">
            <span>Provider</span>
            <select
              value={value.provider}
              onChange={e => handleProviderChange(e.target.value)}
              aria-label="Provider"
            >
              {providers.map(provider => (
                <option key={provider.name} value={provider.name}>{provider.display_name || provider.name}</option>
              ))}
            </select>
          </label>
          <label className="model-selector-field">
            <span>Model</span>
            <select
              value={value.model}
              onChange={e => handleModelChange(e.target.value)}
              aria-label="Model"
            >
              {currentModels.map(model => (
                <option key={model.name} value={model.name}>
                  {model.name}{model.supports_vision ? ' · vision' : ''}
                </option>
              ))}
            </select>
          </label>
          <p className="model-selector-hint">模型切换仅影响后续消息，不会修改全局默认配置。</p>
        </div>
      )}
    </div>
  )
}
