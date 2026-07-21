import { describe, expect, it } from 'vitest'
import { formatPlaybackTime, resolveVoiceOutputMode, voiceModeLabel } from './voiceOutput'
import type { VoiceCapabilities } from '../services/api'

describe('voiceOutput helpers', () => {
  it('formats playback seconds', () => {
    expect(formatPlaybackTime(65)).toBe('01:05')
    expect(formatPlaybackTime(Number.NaN)).toBe('00:00')
  })

  it('labels output modes', () => {
    expect(voiceModeLabel('server')).toContain('服务端')
    expect(voiceModeLabel('browser')).toContain('浏览器')
  })

  it('prefers server TTS when configured', () => {
    const caps: VoiceCapabilities = {
      provider: 'fake',
      stt: { status: 'configured', model: 'x', formats: [], max_upload_bytes: 1, max_duration_seconds: 1 },
      tts: { status: 'configured', model: 'y', voice: 'z', formats: ['mp3'], max_text_chars: 10 },
      browser_fallback: true,
    }
    expect(resolveVoiceOutputMode(caps)).toBe('server')
  })
})
