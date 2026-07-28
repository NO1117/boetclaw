import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Eye, EyeOff, HelpCircle, Loader2 } from 'lucide-react'
import {
  fetchDefaultProviderConfig,
  fetchProviderModels,
  fetchProviders,
  type ModelInfo,
  type ProviderInfo,
} from '../services/api'
import {
  capabilityTags,
  checkModelCompatibility,
  deriveInputRequirements,
} from '../utils/modelCapabilities'
import './RunMetricsCard.css'

export interface ModelSelection {
  provider: string
  model: string
  supportsVision: boolean | null
  label: string
}

interface PendingAttachment {
  kind: string
}

interface ModelSelectorProps {
  value: ModelSelection | null
  onChange: (selection: ModelSelection | null) => void
  disabled?: boolean
  pendingAttachments?: PendingAttachment[]
}

function buildLabel(provider: string, model: string): string {
  return `${provider} / ${model}`
}

function visionKnown(model: ModelInfo): boolean | null {
  const caps = model.capabilities?.vision
  if (caps === 'true') return true
  if (caps === 'false') return false
  if (model.supports_vision === true) return true
  if (model.supports_vision === false) return false
  return null
}

export default function ModelSelector({
  value,
  onChange,
  disabled,
  pendingAttachments = [],
}: ModelSelectorProps) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelInfo[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)

  const requirements = useMemo(
    () => deriveInputRequirements(pendingAttachments),
    [pendingAttachments],
  )

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
            const info = models.find(m => m.name === model)
            onChange({
              provider: provider.name,
              model,
              supportsVision: info ? visionKnown(info) : null,
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

  const flatModels = useMemo(() => {
    const items: Array<{ provider: ProviderInfo; model: ModelInfo }> = []
    for (const provider of providers) {
      for (const model of modelsByProvider[provider.name] ?? []) {
        items.push({ provider, model })
      }
    }
    return items
  }, [providers, modelsByProvider])

  const compatibilityMap = useMemo(() => {
    const map = new Map<string, ReturnType<typeof checkModelCompatibility>>()
    for (const { provider, model } of flatModels) {
      map.set(`${provider.name}:${model.name}`, checkModelCompatibility(model, requirements))
    }
    return map
  }, [flatModels, requirements])

  const inputAlert = requirements.imageCount > 0
    ? `已检测到 ${requirements.imageCount} 张图片 · 需要视觉理解能力`
    : ''

  const selectModel = (providerName: string, modelName: string) => {
    const model = (modelsByProvider[providerName] ?? []).find(m => m.name === modelName)
    const provider = providers.find(p => p.name === providerName)
    if (!model) return
    const compat = compatibilityMap.get(`${providerName}:${modelName}`)
    if (compat?.status === 'incompatible') return
    onChange({
      provider: providerName,
      model: modelName,
      supportsVision: visionKnown(model),
      label: buildLabel(provider?.display_name || providerName, modelName),
    })
    setOpen(false)
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

  const currentCompat = compatibilityMap.get(`${value.provider}:${value.model}`)

  return (
    <div className={`model-selector-wrap${open ? ' open' : ''}`}>
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
          {value.supportsVision === true ? (
            <Eye size={14} aria-label="支持视觉" />
          ) : value.supportsVision === false ? (
            <EyeOff size={14} aria-label="不支持视觉" />
          ) : (
            <HelpCircle size={14} aria-label="视觉能力未知" />
          )}
          <ChevronDown size={14} aria-hidden />
        </button>
      </div>

      {open && (
        <div className="model-selector-panel" role="listbox" aria-label="模型能力选择">
          <div className="model-selector-title">选择适合当前输入的模型</div>
          {inputAlert && <div className="model-selector-alert">{inputAlert}</div>}

          {flatModels.map(({ provider, model }) => {
            const key = `${provider.name}:${model.name}`
            const compat = compatibilityMap.get(key)!
            const selected = value.provider === provider.name && value.model === model.name
            const tags = capabilityTags(model)
            const tagClass = compat.status === 'unknown_risk'
              ? 'model-option-tags unknown'
              : compat.status === 'incompatible'
                ? 'model-option-tags muted'
                : 'model-option-tags'

            return (
              <button
                key={key}
                type="button"
                role="option"
                aria-selected={selected}
                disabled={compat.status === 'incompatible'}
                aria-disabled={compat.status === 'incompatible'}
                className={`model-option${selected ? ' selected' : ''}${compat.status === 'incompatible' ? ' incompatible' : ''}`}
                onClick={() => selectModel(provider.name, model.name)}
              >
                <div className="model-option-name">
                  {model.name}{selected ? '  ✓ 当前选择' : ''}
                </div>
                <div className={tagClass}>{tags.join('   ')}</div>
                <div className={`model-option-reason${
                  compat.status === 'incompatible' ? ' error' : compat.status === 'unknown_risk' ? ' warn' : ''
                }`}>
                  {compat.reason}
                </div>
              </button>
            )
          })}

          {requirements.imageCount > 0 && (
            <div className="model-selector-guidance">
              <div className="model-selector-guidance-title">提示</div>
              <div className="model-selector-guidance-body">
                移除图片后，所有文本模型会重新变为可选。
              </div>
            </div>
          )}

          {currentCompat?.status === 'unknown_risk' && (
            <div className="model-selector-guidance">
              <div className="model-selector-guidance-title">兼容性风险</div>
              <div className="model-selector-guidance-body">{currentCompat.reason}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
