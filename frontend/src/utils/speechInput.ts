export type SpeechInputState =
  | 'idle'
  | 'listening'
  | 'unsupported'
  | 'permission-denied'
  | 'error'

export interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

export interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
}

export function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

export function createSpeechRecognition(lang = 'zh-CN'): SpeechRecognitionLike | null {
  const Ctor = getSpeechRecognitionCtor()
  if (!Ctor) return null
  const recognition = new Ctor()
  recognition.lang = lang
  recognition.continuous = true
  recognition.interimResults = true
  return recognition
}

export function mapSpeechError(error?: string): SpeechInputState {
  if (error === 'not-allowed' || error === 'service-not-allowed') return 'permission-denied'
  if (error === 'audio-capture' || error === 'network') return 'error'
  return 'error'
}

export function mergeTranscript(
  base: string,
  results: SpeechRecognitionEventLike['results'],
  fromIndex: number,
): { text: string; interim: string } {
  let finalPart = ''
  let interim = ''
  for (let i = fromIndex; i < results.length; i += 1) {
    const chunk = results[i][0]?.transcript ?? ''
    if (results[i].isFinal) finalPart += chunk
    else interim += chunk
  }
  const trimmedBase = base.trimEnd()
  const prefix = trimmedBase ? `${trimmedBase} ` : ''
  return {
    text: finalPart ? `${prefix}${finalPart}`.trim() : trimmedBase,
    interim: interim ? `${prefix}${finalPart}${interim}`.trim() : '',
  }
}
