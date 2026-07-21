export const ATTACHMENT_LIMITS = {
  maxFileBytes: 25 * 1024 * 1024,
  maxFiles: 20,
  maxTotalBytes: 100 * 1024 * 1024,
} as const

export type AttachmentKind = 'text' | 'image' | 'binary' | 'document'
export type AttachmentStatus =
  | 'pending'
  | 'uploading'
  | 'uploaded'
  | 'parsing'
  | 'ready'
  | 'failed'
  | 'error'
  | 'cancelled'

import type { AttachmentRecordDto } from '../services/api'

export interface QueuedAttachment {
  id: string
  localKey: string
  file: File
  relativePath: string
  kind: AttachmentKind
  status: AttachmentStatus
  statusMessage: string
  mimeType: string
  size: number
  progress: number
  attachmentId?: string
  record?: AttachmentRecordDto
  abortController?: AbortController
}

export interface ChatAttachmentPayload {
  filename: string
  relative_path: string
  mime_type: string
  size: number
  kind: AttachmentKind
  content_base64: string
}

const TEXT_EXTENSIONS = new Set([
  '.txt', '.md', '.markdown', '.json', '.yaml', '.yml', '.csv', '.tsv', '.xml',
  '.html', '.htm', '.js', '.ts', '.jsx', '.tsx', '.py', '.java', '.go', '.rs',
  '.sql', '.sh', '.bat', '.ps1', '.log', '.ini', '.cfg', '.env',
])

const DOCUMENT_EXTENSIONS = new Set(['.pdf', '.docx', '.xlsx', '.pptx'])

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function inferAttachmentKind(file: File): AttachmentKind {
  const mime = (file.type || '').toLowerCase()
  if (mime.startsWith('image/')) return 'image'
  if (mime === 'application/pdf' || DOCUMENT_EXTENSIONS.has(extensionOf(file.name))) return 'document'
  if (mime.startsWith('text/') || mime === 'application/json' || mime === 'application/xml') return 'text'
  const lower = file.name.toLowerCase()
  for (const ext of TEXT_EXTENSIONS) {
    if (lower.endsWith(ext)) return 'text'
  }
  return 'binary'
}

function extensionOf(name: string): string {
  const lower = name.toLowerCase()
  const dot = lower.lastIndexOf('.')
  return dot >= 0 ? lower.slice(dot) : ''
}

function relativePathFromFile(file: File): string {
  const raw = (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim()
  return raw || file.name
}

export function validateIncomingFile(file: File): string | null {
  if (file.size > ATTACHMENT_LIMITS.maxFileBytes) {
    return `${file.name} 超过单文件 25 MB 限制`
  }
  const path = relativePathFromFile(file)
  if (path.includes('..') || path.startsWith('/') || path.includes('\\')) {
    return `${file.name} 路径无效`
  }
  return null
}

export function validateQueue(queue: QueuedAttachment[]): string | null {
  if (queue.length > ATTACHMENT_LIMITS.maxFiles) {
    return `最多添加 ${ATTACHMENT_LIMITS.maxFiles} 个附件`
  }
  const total = queue.reduce((sum, item) => sum + item.size, 0)
  if (total > ATTACHMENT_LIMITS.maxTotalBytes) {
    return '附件总大小超过 100 MB 限制'
  }
  return null
}

export function isAttachmentSendReady(item: QueuedAttachment): boolean {
  return item.status === 'ready' && Boolean(item.attachmentId)
}

export function documentSummaryLabel(record?: { summary?: Record<string, unknown> }): string {
  const summary = record?.summary as {
    page_count?: number
    sheet_count?: number
    slide_count?: number
    chunk_count?: number
    searchable?: boolean
  } | undefined
  if (!summary) return ''
  const parts: string[] = []
  if (summary.page_count) parts.push(`${summary.page_count} 页`)
  if (summary.sheet_count) parts.push(`${summary.sheet_count} 表`)
  if (summary.slide_count) parts.push(`${summary.slide_count} 幻灯片`)
  if (summary.chunk_count) parts.push(`${summary.chunk_count} 块`)
  if (summary.searchable) parts.push('可检索')
  return parts.join(' · ')
}

export function scanStatusLabel(scanStatus: 'unscanned' | 'clean' | 'infected' | 'error'): string {
  if (scanStatus === 'unscanned') return '未扫描'
  if (scanStatus === 'clean') return '已扫描'
  if (scanStatus === 'infected') return '风险'
  return '扫描异常'
}

export function statusMessageForRecord(record: { status: string; error_summary?: string; summary?: Record<string, unknown>; scan_status: 'unscanned' | 'clean' | 'infected' | 'error' }): string {
  if (record.status === 'ready') {
    const doc = documentSummaryLabel(record)
    const scan = scanStatusLabel(record.scan_status)
    return doc ? `${doc} · ${scan}` : scan
  }
  if (record.status === 'parsing') return '解析中…'
  if (record.status === 'uploaded') return '已上传，等待解析'
  if (record.status === 'failed') return record.error_summary || '解析失败'
  return record.status
}

export async function buildQueueItem(file: File): Promise<QueuedAttachment> {
  const relativePath = relativePathFromFile(file)
  const kind = inferAttachmentKind(file)
  const localKey = `${relativePath}-${file.size}-${file.lastModified}`
  return {
    id: localKey,
    localKey,
    file,
    relativePath,
    kind,
    status: 'pending',
    statusMessage: '等待上传',
    mimeType: file.type || 'application/octet-stream',
    size: file.size,
    progress: 0,
  }
}

export async function filesToQueue(files: FileList | File[]): Promise<{ queue: QueuedAttachment[]; errors: string[] }> {
  const queue: QueuedAttachment[] = []
  const errors: string[] = []
  const list = Array.from(files)
  for (const file of list) {
    const err = validateIncomingFile(file)
    if (err) {
      errors.push(err)
      continue
    }
    queue.push(await buildQueueItem(file))
  }
  return { queue, errors }
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(new Error(`无法读取 ${file.name}`))
    reader.readAsDataURL(file)
  })
}

/** Legacy inline Base64 path — kept for compatibility tests. */
export async function encodeAttachmentsForRequest(queue: QueuedAttachment[]): Promise<ChatAttachmentPayload[]> {
  const encoded: ChatAttachmentPayload[] = []
  for (const item of queue) {
    if (!isAttachmentSendReady(item)) continue
    encoded.push({
      filename: item.file.name,
      relative_path: item.relativePath === item.file.name ? '' : item.relativePath,
      mime_type: item.mimeType,
      size: item.size,
      kind: item.kind === 'document' ? 'text' : item.kind,
      content_base64: await readFileAsBase64(item.file),
    })
  }
  return encoded
}

export function attachmentIdsForRequest(queue: QueuedAttachment[]): string[] {
  return queue.filter(isAttachmentSendReady).map(item => item.attachmentId!).filter(Boolean)
}

export function attachmentSummaryLabel(item: QueuedAttachment): string {
  const path = item.relativePath || item.file.name
  return `${path} · ${formatBytes(item.size)}`
}

export interface MessageAttachmentSummary {
  filename: string
  sizeLabel: string
  kind: AttachmentKind
  attachmentId?: string
  citation?: string
}

export function parseAttachmentSummariesFromContent(content: string): MessageAttachmentSummary[] {
  const lines = content.split('\n').filter(line => line.startsWith('▧ '))
  return lines.map(line => {
    const body = line.slice(2)
    const idMatch = body.match(/id:([A-Za-z0-9_-]+)/)
    const cleaned = body.replace(/\s·\sid:[A-Za-z0-9_-]+/, '')
    const [name, sizeLabel = ''] = cleaned.split(' · ')
    const lower = name.toLowerCase()
    let kind: AttachmentKind = 'binary'
    if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(lower)) kind = 'image'
    else if (/\.(pdf|docx|xlsx|pptx)$/i.test(lower)) kind = 'document'
    else if (/\.(txt|md|json|ya?ml|csv|xml|html?|py|js|ts)$/i.test(lower)) kind = 'text'
    return {
      filename: name.trim(),
      sizeLabel: sizeLabel.trim(),
      kind,
      attachmentId: idMatch?.[1],
    }
  })
}

export function stripAttachmentSummaryLines(content: string): string {
  return content.split('\n').filter(line => !line.startsWith('▧ ')).join('\n').trim()
}

export async function pollAttachmentUntilReady(
  fetchRecord: (attachmentId: string) => Promise<AttachmentRecordDto>,
  attachmentId: string,
  onUpdate?: (record: AttachmentRecordDto) => void,
  timeoutMs = 60_000,
): Promise<AttachmentRecordDto> {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const record = await fetchRecord(attachmentId)
    onUpdate?.(record)
    if (record.status === 'ready' || record.status === 'failed') return record
    await new Promise(resolve => window.setTimeout(resolve, 400))
  }
  throw new Error('附件解析超时')
}
