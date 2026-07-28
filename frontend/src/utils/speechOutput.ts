export type SpeechPlaybackState = 'idle' | 'playing' | 'paused' | 'unsupported'

export function stripMarkdownForSpeech(input: string): string {
  return input
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/(\*\*|__|\*|_|~~)/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

export class SpeechPlaybackController {
  state: SpeechPlaybackState = isSpeechSynthesisSupported() ? 'idle' : 'unsupported'

  cancel(): void {
    if (!isSpeechSynthesisSupported()) return
    window.speechSynthesis.cancel()
    this.state = 'idle'
  }

  speak(text: string, lang = 'zh-CN'): SpeechPlaybackState {
    if (!isSpeechSynthesisSupported()) {
      this.state = 'unsupported'
      return this.state
    }
    this.cancel()
    const utterance = new SpeechSynthesisUtterance(stripMarkdownForSpeech(text))
    utterance.lang = lang
    utterance.onend = () => {
      this.state = 'idle'
    }
    utterance.onerror = () => {
      this.state = 'idle'
    }
    window.speechSynthesis.speak(utterance)
    this.state = 'playing'
    return this.state
  }

  pause(): SpeechPlaybackState {
    if (!isSpeechSynthesisSupported()) return 'unsupported'
    if (this.state !== 'playing') return this.state
    window.speechSynthesis.pause()
    this.state = 'paused'
    return this.state
  }

  resume(): SpeechPlaybackState {
    if (!isSpeechSynthesisSupported()) return 'unsupported'
    if (this.state !== 'paused') return this.state
    window.speechSynthesis.resume()
    this.state = 'playing'
    return this.state
  }

  stop(): SpeechPlaybackState {
    this.cancel()
    return this.state
  }
}
