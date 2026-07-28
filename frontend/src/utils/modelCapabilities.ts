import type { ModelInfo } from '../services/api'

export type CapabilityTriState = 'true' | 'false' | 'unknown'
export type CompatibilityStatus = 'compatible' | 'incompatible' | 'unknown_risk'

export interface InputRequirements {
  requiresVision: boolean
  imageCount: number
  documentCount: number
  attachmentCount: number
}

export interface CompatibilityResult {
  status: CompatibilityStatus
  missingCapabilities: string[]
  warnings: string[]
  reason: string
}

export interface RunMetricsSummary {
  trace_id: string
  run_id: string
  agent_id?: string
  provider?: string | null
  model?: string | null
  status?: string
  time_to_first_token_ms?: number | null
  total_duration_ms?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  estimated_cost?: number | null
  cost_currency?: string | null
  cost_is_estimate?: boolean
  graph_cache_hit?: boolean | null
  attachment_count?: number
  retrieval_hits?: number
}

function tri(model: ModelInfo, key: keyof NonNullable<ModelInfo['capabilities']>): CapabilityTriState {
  const caps = model.capabilities
  if (caps && caps[key]) return caps[key] as CapabilityTriState
  if (key === 'vision') {
    if (model.supports_vision === true) return 'true'
    if (model.supports_vision === false) return 'false'
    return 'unknown'
  }
  if (key === 'tools') {
    if (model.supports_tools === true) return 'true'
    if (model.supports_tools === false) return 'false'
    return 'unknown'
  }
  return 'unknown'
}

export function deriveInputRequirements(
  attachments: Array<{ kind: string }>,
): InputRequirements {
  const imageCount = attachments.filter(a => a.kind === 'image').length
  const documentCount = attachments.filter(a => a.kind === 'text' || a.kind === 'document').length
  return {
    requiresVision: imageCount > 0,
    imageCount,
    documentCount,
    attachmentCount: attachments.length,
  }
}

export function checkModelCompatibility(
  model: ModelInfo,
  requirements: InputRequirements,
): CompatibilityResult {
  const missing: string[] = []
  const warnings: string[] = []

  if (requirements.requiresVision) {
    const vision = tri(model, 'vision')
    if (vision === 'false') missing.push('vision')
    else if (vision === 'unknown') {
      warnings.push('模型视觉能力未知，发送前请确认兼容性')
    }
  }

  if (missing.length > 0) {
    return {
      status: 'incompatible',
      missingCapabilities: missing,
      warnings,
      reason: '不可选：当前图片需要视觉能力',
    }
  }
  if (warnings.length > 0) {
    return {
      status: 'unknown_risk',
      missingCapabilities: missing,
      warnings,
      reason: warnings[0],
    }
  }
  return {
    status: 'compatible',
    missingCapabilities: [],
    warnings: [],
    reason: '与当前输入兼容',
  }
}

export function formatContextWindow(value: number | null | undefined): string {
  if (value == null || value <= 0) return '上下文未知'
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000)}M 上下文`
  if (value >= 1000) return `${Math.round(value / 1000)}K 上下文`
  return `${value} 上下文`
}

export function capabilityTags(model: ModelInfo): string[] {
  const tags: string[] = []
  const vision = tri(model, 'vision')
  if (vision === 'true') tags.push('视觉')
  else if (vision === 'unknown') tags.push('视觉能力未知')
  if (tri(model, 'tools') === 'true') tags.push('工具')
  if (tri(model, 'structured_output') === 'true') tags.push('JSON')
  if (tri(model, 'is_local') === 'true') tags.push('本地')
  tags.push(formatContextWindow(model.context_window))
  return tags
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null) return '暂无数据'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatTokenCount(value: number | null | undefined): string {
  if (value == null) return '暂无数据'
  return value.toLocaleString('zh-CN')
}

export function formatEstimatedCost(metrics: RunMetricsSummary): string {
  if (metrics.estimated_cost == null) return '暂无数据'
  const currency = metrics.cost_currency === 'USD' ? '$' : (metrics.cost_currency ?? '')
  const amount = metrics.estimated_cost.toFixed(metrics.estimated_cost < 0.01 ? 4 : 3)
  return `${currency}${amount}${metrics.cost_is_estimate ? ' · 仅供参考' : ''}`
}

export function graphCacheLabel(hit: boolean | null | undefined): string {
  if (hit === true) return '图缓存命中'
  if (hit === false) return '图缓存未命中'
  return '图缓存 —'
}
