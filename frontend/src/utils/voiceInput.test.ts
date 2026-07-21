import { describe, expect, it, vi } from 'vitest'
import { appendTranscript, extensionForMime, resolveVoiceInputMode } from './voiceInput'
import type { VoiceCapabilities } from '../services/api'

describe('voiceInput helpers', () => {
  it('appendTranscript merges without overwriting existing text', () => {
    expect(appendTranscript('已有内容', '新增一句')).toBe('已有内容 新增一句')
    expect(appendTranscript('', '首句')).toBe('首句')
  })

  it('maps mime type to extension', () => {
    expect(extensionForMime('audio/webm;codecs=opus')).toBe('webm')
    expect(extensionForMime('audio/ogg')).toBe('ogg')
  })

  it('prefers server mode when STT configured and MediaRecorder exists', () => {
    const caps: VoiceCapabilities = {
      provider: 'fake',
      stt: {
        status: 'configured',
        model: 'fake-stt',
        formats: ['webm'],
        max_upload_bytes: 1000,
        max_duration_seconds: 60,
      },
      tts: {
        status: 'configured',
        model: 'fake-tts',
        voice: 'alloy',
        formats: ['mp3'],
        max_text_chars: 100,
      },
      browser_fallback: true,
    }
    vi.stubGlobal('MediaRecorder', class {
      static isTypeSupported() { return true }
    })
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: async () => ({ getTracks: () => [] }) },
    })
    expect(resolveVoiceInputMode(caps)).toBe('server')
  })
})
