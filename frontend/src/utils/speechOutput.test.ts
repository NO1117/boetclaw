import { describe, expect, it, vi } from 'vitest'
import { SpeechPlaybackController, stripMarkdownForSpeech } from './speechOutput'

class FakeUtterance {
  lang = 'zh-CN'
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(public text: string) {}
}

describe('speechOutput', () => {
  it('strips markdown before speaking', () => {
    expect(stripMarkdownForSpeech('# Title\n**bold** `code`')).toBe('Title bold code')
  })

  it('tracks play/pause/stop states when supported', () => {
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: {
        speak: vi.fn(),
        cancel: vi.fn(),
        pause: vi.fn(),
        resume: vi.fn(),
      },
    })
    const controller = new SpeechPlaybackController()
    expect(controller.speak('hello')).toBe('playing')
    expect(controller.pause()).toBe('paused')
    expect(controller.resume()).toBe('playing')
    expect(controller.stop()).toBe('idle')
  })
})
