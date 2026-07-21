import { describe, expect, it } from 'vitest'
import {
  ATTACHMENT_LIMITS,
  attachmentIdsForRequest,
  buildQueueItem,
  encodeAttachmentsForRequest,
  filesToQueue,
  inferAttachmentKind,
  isAttachmentSendReady,
  parseAttachmentSummariesFromContent,
  validateIncomingFile,
  validateQueue,
  type QueuedAttachment,
} from './attachments'

describe('attachments utils', () => {
  it('rejects oversized files', () => {
    const file = new File(['x'], 'big.bin', { type: 'application/octet-stream' })
    Object.defineProperty(file, 'size', { value: ATTACHMENT_LIMITS.maxFileBytes + 1 })
    expect(validateIncomingFile(file)).toMatch(/25 MB/)
  })

  it('builds queue items with inferred kinds', async () => {
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    const item = await buildQueueItem(file)
    expect(item.kind).toBe('text')
    expect(item.status).toBe('pending')
  })

  it('validates aggregate limits', async () => {
    const queue = await Promise.all(
      Array.from({ length: 21 }, (_, i) => buildQueueItem(new File(['a'], `f${i}.txt`, { type: 'text/plain' }))),
    )
    expect(validateQueue(queue)).toMatch(/20/)
  })

  it('requires ready attachment id before send', () => {
    const pending: QueuedAttachment = {
      id: '1',
      localKey: '1',
      file: new File(['a'], 'a.txt'),
      relativePath: 'a.txt',
      kind: 'text',
      status: 'pending',
      statusMessage: '',
      mimeType: 'text/plain',
      size: 1,
      progress: 0,
    }
    expect(isAttachmentSendReady(pending)).toBe(false)
    expect(attachmentIdsForRequest([{ ...pending, status: 'ready', attachmentId: 'abc' }])).toEqual(['abc'])
  })

  it('encodes ready attachments for legacy API payload', async () => {
    const { queue } = await filesToQueue([new File(['# hi'], 'readme.md', { type: 'text/markdown' })])
    const ready = [{ ...queue[0], status: 'ready' as const, attachmentId: 'id1', progress: 100 }]
    const encoded = await encodeAttachmentsForRequest(ready)
    expect(encoded).toHaveLength(1)
    expect(encoded[0].filename).toBe('readme.md')
    expect(encoded[0].content_base64).toBeTruthy()
  })

  it('detects image mime types', () => {
    const file = new File([''], 'a.png', { type: 'image/png' })
    expect(inferAttachmentKind(file)).toBe('image')
  })

  it('parses attachment id from history summary lines', () => {
    const parsed = parseAttachmentSummariesFromContent('▧ report.txt · 12 B · id:abc12345')
    expect(parsed[0].attachmentId).toBe('abc12345')
  })
})
