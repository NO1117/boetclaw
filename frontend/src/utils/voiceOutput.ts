/** Voice output: server TTS streaming with browser speechSynthesis fallback. */

import { synthesizeVoiceSpeech, fetchVoiceCapabilities, type VoiceCapabilities } from '../services/api'
import {
  isSpeechSynthesisSupported,
  SpeechPlaybackController,
  stripMarkdownForSpeech,
  type SpeechPlaybackState,
} from './speechOutput'

export type VoiceOutputMode = 'server' | 'browser' | 'none'

export interface VoicePlaybackProgress {
  current: number
  duration: number
}

export function resolveVoiceOutputMode(caps: VoiceCapabilities | null): VoiceOutputMode {
  if (caps?.tts?.status === 'configured') return 'server'
  if (isSpeechSynthesisSupported()) return 'browser'
  return 'none'
}

export function voiceModeLabel(mode: VoiceOutputMode): string {
  if (mode === 'server') return '服务端高质量'
  if (mode === 'browser') return '浏览器本地'
  return '不可用'
}

export class VoicePlaybackController {
  mode: VoiceOutputMode = 'none'
  state: SpeechPlaybackState = isSpeechSynthesisSupported() ? 'idle' : 'unsupported'
  progress: VoicePlaybackProgress = { current: 0, duration: 0 }
  objectUrl: string | null = null
  audio: HTMLAudioElement | null = null
  private browser = new SpeechPlaybackController()
  private abortController: AbortController | null = null
  private caps: VoiceCapabilities | null = null
  private onState?: (state: SpeechPlaybackState) => void
  private onProgress?: (progress: VoicePlaybackProgress) => void

  setCallbacks(
    onState: (state: SpeechPlaybackState) => void,
    onProgress?: (progress: VoicePlaybackProgress) => void,
  ): void {
    this.onState = onState
    this.onProgress = onProgress
  }

  async loadCapabilities(): Promise<VoiceCapabilities | null> {
    try {
      this.caps = await fetchVoiceCapabilities()
    } catch {
      this.caps = null
    }
    this.mode = resolveVoiceOutputMode(this.caps)
    return this.caps
  }

  getCapabilities(): VoiceCapabilities | null {
    return this.caps
  }

  private emitState(state: SpeechPlaybackState): void {
    this.state = state
    this.onState?.(state)
  }

  private emitProgress(): void {
    this.onProgress?.({ ...this.progress })
  }

  private releaseObjectUrl(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl)
      this.objectUrl = null
    }
  }

  cancel(): void {
    this.abortController?.abort()
    this.abortController = null
    if (this.audio) {
      this.audio.pause()
      this.audio.src = ''
      this.audio = null
    }
    this.releaseObjectUrl()
    this.browser.cancel()
    this.progress = { current: 0, duration: 0 }
    this.emitProgress()
    this.emitState(isSpeechSynthesisSupported() || this.mode === 'server' ? 'idle' : 'unsupported')
  }

  async speak(text: string, lang = 'zh-CN'): Promise<SpeechPlaybackState> {
    this.cancel()
    if (!this.caps) await this.loadCapabilities()
    this.mode = resolveVoiceOutputMode(this.caps)
    const plain = stripMarkdownForSpeech(text)
    if (!plain) {
      this.emitState('idle')
      return this.state
    }

    if (this.mode === 'server') {
      return this.speakServer(plain, lang)
    }
    if (this.mode === 'browser') {
      this.emitState(this.browser.speak(plain, lang))
      return this.state
    }
    this.emitState('unsupported')
    return this.state
  }

  private async speakServer(text: string, lang: string): Promise<SpeechPlaybackState> {
    this.abortController = new AbortController()
    try {
      const blob = await synthesizeVoiceSpeech(
        { text, language: lang, format: 'mp3' },
        this.abortController.signal,
      )
      if (this.abortController.signal.aborted) {
        this.emitState('idle')
        return this.state
      }
      this.releaseObjectUrl()
      this.objectUrl = URL.createObjectURL(blob)
      const audio = new Audio(this.objectUrl)
      this.audio = audio
      audio.addEventListener('loadedmetadata', () => {
        this.progress.duration = Number.isFinite(audio.duration) ? audio.duration : 0
        this.emitProgress()
      })
      audio.addEventListener('timeupdate', () => {
        this.progress.current = audio.currentTime
        if (Number.isFinite(audio.duration)) this.progress.duration = audio.duration
        this.emitProgress()
      })
      audio.addEventListener('ended', () => {
        this.emitState('idle')
        this.releaseObjectUrl()
        this.audio = null
      })
      audio.addEventListener('error', () => {
        this.emitState('idle')
      })
      await audio.play()
      this.emitState('playing')
      return this.state
    } catch {
      if (this.abortController?.signal.aborted) {
        this.emitState('idle')
        return this.state
      }
      if (isSpeechSynthesisSupported()) {
        this.mode = 'browser'
        this.emitState(this.browser.speak(text, lang))
        return this.state
      }
      this.emitState('unsupported')
      return this.state
    } finally {
      this.abortController = null
    }
  }

  pause(): SpeechPlaybackState {
    if (this.mode === 'server' && this.audio && this.state === 'playing') {
      this.audio.pause()
      this.emitState('paused')
      return this.state
    }
    this.emitState(this.browser.pause())
    return this.state
  }

  resume(): SpeechPlaybackState {
    if (this.mode === 'server' && this.audio && this.state === 'paused') {
      void this.audio.play()
      this.emitState('playing')
      return this.state
    }
    this.emitState(this.browser.resume())
    return this.state
  }

  stop(): SpeechPlaybackState {
    this.cancel()
    return this.state
  }

  seek(ratio: number): void {
    if (this.mode !== 'server' || !this.audio || !Number.isFinite(this.audio.duration)) return
    this.audio.currentTime = Math.max(0, Math.min(1, ratio)) * this.audio.duration
  }

  downloadFilename(): string {
    return `speech-${Date.now()}.mp3`
  }

  async downloadBlob(): Promise<Blob | null> {
    if (this.objectUrl) {
      const res = await fetch(this.objectUrl)
      return res.blob()
    }
    return null
  }
}

export function formatPlaybackTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(Math.floor(seconds % 60)).padStart(2, '0')
  return `${mm}:${ss}`
}
