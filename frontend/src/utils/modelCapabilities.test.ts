import { describe, expect, it } from 'vitest'
import {
  capabilityTags,
  checkModelCompatibility,
  deriveInputRequirements,
  formatDurationMs,
  formatEstimatedCost,
  formatTokenCount,
} from './modelCapabilities'
import type { ModelInfo } from '../services/api'

const visionModel: ModelInfo = {
  name: 'gpt-4o',
  provider: 'openai',
  context_window: 128000,
  supports_tools: true,
  supports_vision: true,
  capabilities: {
    vision: 'true',
    tools: 'true',
    audio_input: 'unknown',
    audio_output: 'unknown',
    structured_output: 'true',
    is_local: 'false',
  },
}

const textOnlyModel: ModelInfo = {
  name: 'o1',
  provider: 'openai',
  context_window: 200000,
  supports_tools: false,
  supports_vision: false,
  capabilities: {
    vision: 'false',
    tools: 'false',
    audio_input: 'unknown',
    audio_output: 'unknown',
    structured_output: 'true',
    is_local: 'false',
  },
}

const unknownVisionModel: ModelInfo = {
  name: 'local-llama',
  provider: 'ollama',
  context_window: 128000,
  supports_tools: null,
  supports_vision: null,
  capabilities: {
    vision: 'unknown',
    tools: 'true',
    audio_input: 'unknown',
    audio_output: 'unknown',
    structured_output: 'unknown',
    is_local: 'true',
  },
}

describe('modelCapabilities', () => {
  it('marks non-vision model incompatible for images', () => {
    const req = deriveInputRequirements([{ kind: 'image' }])
    const result = checkModelCompatibility(textOnlyModel, req)
    expect(result.status).toBe('incompatible')
    expect(result.missingCapabilities).toContain('vision')
  })

  it('allows unknown vision with warning', () => {
    const req = deriveInputRequirements([{ kind: 'image' }])
    const result = checkModelCompatibility(unknownVisionModel, req)
    expect(result.status).toBe('unknown_risk')
    expect(result.warnings.length).toBeGreaterThan(0)
  })

  it('builds capability tags', () => {
    expect(capabilityTags(visionModel)).toContain('视觉')
    expect(capabilityTags(unknownVisionModel)).toContain('视觉能力未知')
  })

  it('formats empty metrics as 暂无数据', () => {
    expect(formatDurationMs(null)).toBe('暂无数据')
    expect(formatTokenCount(null)).toBe('暂无数据')
    expect(formatEstimatedCost({ trace_id: 't', run_id: 'r', estimated_cost: null })).toBe('暂无数据')
  })
})
