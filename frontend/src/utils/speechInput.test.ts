import { describe, expect, it } from 'vitest'
import { getSpeechRecognitionCtor } from './speechInput'

describe('speechInput', () => {
  it('returns null when browser speech recognition is unavailable', () => {
    expect(getSpeechRecognitionCtor()).toBeNull()
  })
})
