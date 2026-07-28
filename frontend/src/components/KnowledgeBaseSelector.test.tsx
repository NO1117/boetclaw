import { describe, expect, it } from 'vitest'
import { knowledgeBaseIdsForRequest } from './KnowledgeBaseSelector'

describe('knowledgeBaseIdsForRequest', () => {
  it('returns undefined for default mode', () => {
    expect(knowledgeBaseIdsForRequest('default', [])).toBeUndefined()
  })

  it('returns empty array when disabled', () => {
    expect(knowledgeBaseIdsForRequest('disabled', [])).toEqual([])
  })

  it('returns explicit ids', () => {
    expect(knowledgeBaseIdsForRequest('explicit', ['kb-1'])).toEqual(['kb-1'])
  })
})
