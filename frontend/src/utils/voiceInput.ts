/** Voice input: MediaRecorder + server STT with browser SpeechRecognition fallback. */

import {
  fetchVoiceCapabilities,
  transcribeVoiceAudio,
  type VoiceCapabilities,
} from '../services/api'
import {
  createSpeechRecognition,
  getSpeechRecognitionCtor,
  mapSpeechError,
  mergeTranscript,
  type SpeechInputState as BrowserSpeechState,
} from './speechInput'

export type VoiceInputMode = 'server' | 'browser' | 'none'

export type VoiceInputState =
  | BrowserSpeechState
  | 'preparing'
  | 'recording'
  | 'uploading'
  | 'transcribing'
  | 'done'
  | 'failed'
  | 'failed'

export function appendTranscript(base: string, addition: string): string {
  const trimmed = addition.trim()
  if (!trimmed) return base
  const trimmedBase = base.trimEnd()
  return trimmedBase ? `${trimmedBase} ${trimmed}` : trimmed
}

export function isMediaRecorderSupported(): boolean {
  return typeof window !== 'undefined'
    && typeof MediaRecorder !== 'undefined'
    && typeof navigator !== 'undefined'
    && !!navigator.mediaDevices?.getUserMedia
}

export function pickRecorderMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ]
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return 'audio/webm'
}

export function extensionForMime(mime: string): string {
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

export function resolveVoiceInputMode(caps: VoiceCapabilities | null): VoiceInputMode {
  if (caps?.stt?.status === 'configured' && isMediaRecorderSupported()) return 'server'
  if (getSpeechRecognitionCtor()) return 'browser'
  return 'none'
}

export interface VoiceInputCallbacks {
  onStateChange: (state: VoiceInputState) => void
  onSecondsChange: (seconds: number) => void
  onPreviewChange: (preview: string) => void
  onTranscript: (text: string, mode: VoiceInputMode) => void
  onError: (message: string) => void
}

export class VoiceInputController {
  private mode: VoiceInputMode = 'none'
  private state: VoiceInputState = 'idle'
  private baseText = ''
  private caps: VoiceCapabilities | null = null
  private mediaStream: MediaStream | null = null
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private timer: number | null = null
  private seconds = 0
  private abortController: AbortController | null = null
  private browserRecognition: ReturnType<typeof createSpeechRecognition> | null = null
  private lastInsert = ''

  constructor(private callbacks: VoiceInputCallbacks) {}

  getState(): VoiceInputState {
    return this.state
  }

  getMode(): VoiceInputMode {
    return this.mode
  }

  getCapabilities(): VoiceCapabilities | null {
    return this.caps
  }

  getLastInsert(): string {
    return this.lastInsert
  }

  async loadCapabilities(): Promise<VoiceCapabilities | null> {
    try {
      this.caps = await fetchVoiceCapabilities()
    } catch {
      this.caps = null
    }
    this.mode = resolveVoiceInputMode(this.caps)
    if (this.mode === 'none' && this.state === 'idle') {
      this.setState(getSpeechRecognitionCtor() ? 'idle' : 'unsupported')
    }
    return this.caps
  }

  async toggle(baseText: string): Promise<void> {
    if (['recording', 'uploading', 'transcribing', 'listening', 'preparing'].includes(this.state)) {
      await this.stop()
      return
    }
    await this.start(baseText)
  }

  async start(baseText: string): Promise<void> {
    this.baseText = baseText
    this.lastInsert = ''
    if (!this.caps) await this.loadCapabilities()
    this.mode = resolveVoiceInputMode(this.caps)
    if (this.mode === 'server') {
      await this.startServerRecording()
      return
    }
    if (this.mode === 'browser') {
      this.startBrowserRecognition()
      return
    }
    this.setState('unsupported')
    this.callbacks.onError('当前环境不支持语音输入')
  }

  async stop(): Promise<void> {
    if (this.mode === 'server' && this.state === 'recording') {
      this.recorder?.stop()
      return
    }
    if (this.mode === 'browser' && this.state === 'listening') {
      this.browserRecognition?.stop()
    }
    this.cleanupServer()
    this.cleanupBrowser()
    this.setState(this.mode === 'none' ? 'unsupported' : 'idle')
    this.callbacks.onPreviewChange('')
  }

  cancel(): void {
    if (this.recorder && this.state === 'recording') {
      this.recorder.onstop = null
      try {
        this.recorder.stop()
      } catch { /* ignore */ }
    }
    this.abortController?.abort()
    this.cleanupServer()
    this.cleanupBrowser()
    this.setState(this.mode === 'none' ? 'unsupported' : 'idle')
    this.callbacks.onPreviewChange('')
  }

  undoLastInsert(currentText: string): string {
    if (!this.lastInsert) return currentText
    const suffix = ` ${this.lastInsert}`
    if (currentText.endsWith(suffix)) return currentText.slice(0, -suffix.length).trimEnd()
    if (currentText.endsWith(this.lastInsert)) return currentText.slice(0, -this.lastInsert.length).trimEnd()
    return currentText
  }

  private setState(state: VoiceInputState): void {
    this.state = state
    this.callbacks.onStateChange(state)
  }

  private startTimer(): void {
    this.seconds = 0
    this.callbacks.onSecondsChange(0)
    this.timer = window.setInterval(() => {
      this.seconds += 1
      this.callbacks.onSecondsChange(this.seconds)
    }, 1000)
  }

  private stopTimer(): void {
    if (this.timer) {
      window.clearInterval(this.timer)
      this.timer = null
    }
  }

  private async startServerRecording(): Promise<void> {
    this.setState('preparing')
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = pickRecorderMimeType()
      this.chunks = []
      this.recorder = new MediaRecorder(this.mediaStream, { mimeType })
      this.recorder.ondataavailable = (event) => {
        if (event.data.size > 0) this.chunks.push(event.data)
      }
      this.recorder.onstop = () => void this.finishServerRecording(mimeType)
      this.recorder.start(250)
      this.setState('recording')
      this.startTimer()
    } catch {
      this.cleanupServer()
      this.setState('permission-denied')
      this.callbacks.onError('无法访问麦克风')
    }
  }

  private async finishServerRecording(mimeType: string): Promise<void> {
    this.stopTimer()
    const blob = new Blob(this.chunks, { type: mimeType })
    this.cleanupServer()
    if (!blob.size) {
      this.setState('failed')
      this.callbacks.onError('未录到有效音频')
      return
    }
    this.setState('uploading')
    this.abortController = new AbortController()
    try {
      const ext = extensionForMime(mimeType)
      const file = new File([blob], `recording.${ext}`, { type: mimeType })
      this.setState('transcribing')
      const result = await transcribeVoiceAudio(file, undefined, this.abortController.signal)
      const merged = appendTranscript(this.baseText, result.text)
      this.lastInsert = result.text.trim()
      this.callbacks.onTranscript(merged, 'server')
      this.callbacks.onPreviewChange('')
      this.setState('done')
      window.setTimeout(() => {
        if (this.state === 'done') this.setState('idle')
      }, 800)
    } catch (err) {
      if (this.abortController?.signal.aborted) {
        this.setState('idle')
        return
      }
      this.setState('failed')
      this.callbacks.onError(err instanceof Error ? err.message : '转写失败')
      if (getSpeechRecognitionCtor()) {
        this.mode = 'browser'
        this.callbacks.onError('服务端转写失败，可尝试浏览器识别')
      }
    } finally {
      this.abortController = null
    }
  }

  private startBrowserRecognition(): void {
    const recognition = createSpeechRecognition('zh-CN')
    if (!recognition) {
      this.setState('unsupported')
      return
    }
    this.browserRecognition = recognition
    recognition.onresult = (event) => {
      const merged = mergeTranscript(this.baseText, event.results, event.resultIndex)
      if (merged.text !== this.baseText) {
        this.baseText = merged.text
        this.callbacks.onTranscript(merged.text, 'browser')
      }
      this.callbacks.onPreviewChange(merged.interim || merged.text)
    }
    recognition.onerror = (event) => {
      this.setState(mapSpeechError(event.error))
      this.cleanupBrowser()
      this.callbacks.onPreviewChange('')
    }
    recognition.onend = () => {
      this.stopTimer()
      this.callbacks.onPreviewChange('')
      this.setState(getSpeechRecognitionCtor() ? 'idle' : 'unsupported')
      this.browserRecognition = null
    }
    try {
      recognition.start()
      this.setState('listening')
      this.startTimer()
    } catch {
      this.setState('error')
    }
  }

  private cleanupServer(): void {
    this.recorder = null
    this.chunks = []
    if (this.mediaStream) {
      for (const track of this.mediaStream.getTracks()) track.stop()
      this.mediaStream = null
    }
  }

  private cleanupBrowser(): void {
    this.browserRecognition?.abort()
    this.browserRecognition = null
    this.stopTimer()
  }

  dispose(): void {
    this.cancel()
  }
}

export function formatRecordingDuration(seconds: number): string {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export function voiceInputBusy(state: VoiceInputState): boolean {
  return ['preparing', 'recording', 'uploading', 'transcribing'].includes(state)
}

export function voiceStatusLabel(state: VoiceInputState, mode: VoiceInputMode): string {
  switch (state) {
    case 'preparing': return '准备录音…'
    case 'recording': return mode === 'server' ? '正在录音' : '正在聆听'
    case 'uploading': return '上传音频…'
    case 'transcribing': return '转写中…'
    case 'done': return '转写完成'
    case 'failed': return '语音失败'
    case 'listening': return '正在聆听'
    default: return ''
  }
}
