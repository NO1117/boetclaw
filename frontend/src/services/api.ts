export {
  cancelAgentRun,
  normalizeStreamEnvelope,
  streamChat,
} from './chatStream'
export type {
  RunCancelResult,
  StreamControl,
  StreamEnvelope,
  StreamStopResult,
} from './chatStream'

const API_BASE = '/api/v1'
const CONSOLE_TOKEN_KEY = 'boetclaw_console_token'

export interface ConsoleAuthStatus {
  login_required: boolean
  authenticated: boolean
  ttl_minutes?: number
  token?: string
}

function consoleAuthHeaders(): HeadersInit {
  const token = localStorage.getItem(CONSOLE_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchConsoleAuthStatus(): Promise<ConsoleAuthStatus> {
  const res = await fetch(`${API_BASE}/auth/status`, {
    headers: consoleAuthHeaders(),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function loginConsole(password: string): Promise<ConsoleAuthStatus> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  if (data.token) localStorage.setItem(CONSOLE_TOKEN_KEY, data.token)
  return data
}

export async function logoutConsole(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    headers: consoleAuthHeaders(),
  })
  localStorage.removeItem(CONSOLE_TOKEN_KEY)
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  traceId?: string
  runId?: string
  attachments?: Array<{
    filename: string
    sizeLabel: string
    kind: 'text' | 'image' | 'binary' | 'document'
    attachmentId?: string
    citation?: string
  }>
}

export interface ChatAttachmentDto {
  filename: string
  relative_path?: string
  mime_type: string
  size: number
  kind: 'text' | 'image' | 'binary'
  content_base64: string
}

export interface AttachmentRecordDto {
  attachment_id: string
  agent_id: string
  filename: string
  relative_path: string
  mime_type: string
  size: number
  kind: 'text' | 'image' | 'binary' | 'document'
  status: 'uploading' | 'uploaded' | 'parsing' | 'ready' | 'failed' | 'expired' | 'deleted'
  scan_status: 'unscanned' | 'clean' | 'infected' | 'error'
  error_summary: string
  summary: Record<string, unknown>
  created_at: string
  updated_at: string
  expires_at: string
}

export interface ChatRequestOptions {
  message: string
  threadId?: string
  agentId?: string
  source?: string
  lang?: string
  attachments?: ChatAttachmentDto[]
  attachment_ids?: string[]
  provider?: string
  model?: string
}

export interface Task {
  id: string
  title: string
  prompt: string
  status: string
  thread_id: string
  trace_id: string
  run_id: string
  result: string
  error: string
  gateway: string
  created_at: string
  updated_at: string
}

export interface ToolInfo {
  name: string
  description: string
  source: string
}

export interface TraceEvent {
  id: string
  trace_id: string
  run_id: string
  event_type: string
  timestamp: string
  data: Record<string, unknown>
}

export interface TimelineEvent {
  sequence: number
  id: string
  timestamp: string
  category: string
  event_type: string
  run_id: string
  summary: string
  offset_ms: number
  delta_ms: number
  data: Record<string, unknown>
}

export interface TraceTimeline {
  trace_id: string
  event_count: number
  run_ids: string[]
  categories: Record<string, number>
  started_at: string
  ended_at: string
  duration_ms: number
  events: TimelineEvent[]
}

export interface Stats {
  tasks: Record<string, number>
  trace_events: number
  event_types: Record<string, number>
}

// ----- Drilling domain -----
export interface Well {
  id: string
  name: string
  field: string
  operator: string
  location: string
  status: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface WellboreSection {
  id: string
  well_id: string
  name: string
  top_depth: number
  bottom_depth: number
  hole_size: string
  start_date: string
  end_date: string
  created_at: string
  updated_at: string
}

export interface DailyReport {
  id: string
  well_id: string
  report_date: string
  depth_start: number
  depth_end: number
  summary: string
  issues: string
  created_at: string
  updated_at: string
}

export interface DrillingParam {
  id: string
  well_id: string
  measured_depth: number
  timestamp: string
  wob: number | null
  rpm: number | null
  rop: number | null
  torque: number | null
  pump_pressure: number | null
  flow_rate: number | null
  source: string
  created_at: string
  updated_at: string
}

export interface LasFile {
  id: string
  well_id: string
  filename: string
  path: string
  status: string
  curves: string[]
  depth_min: number | null
  depth_max: number | null
  imported_at: string
  curve_data_path: string
  quality: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ArtifactInfo {
  id: string
  kind: 'chart' | 'code'
  filename: string
  size: number
  created_at: string
  task_id: string
  trace_id: string
  agent_id: string
  well_id: string
  sha256: string
  preview: string
  url: string
  download_url: string
}

export async function fetchWells(): Promise<Well[]> {
  const res = await fetch(`${API_BASE}/domain/wells`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createWell(data: Partial<Well>): Promise<Well> {
  const res = await fetch(`${API_BASE}/domain/wells`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchWell(id: string): Promise<Well> {
  const res = await fetch(`${API_BASE}/domain/wells/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateWell(id: string, data: Partial<Well>): Promise<Well> {
  const res = await fetch(`${API_BASE}/domain/wells/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteWell(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/domain/wells/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function fetchWellSections(wellId = ''): Promise<WellboreSection[]> {
  const suffix = wellId ? `?well_id=${encodeURIComponent(wellId)}` : ''
  const res = await fetch(`${API_BASE}/domain/sections${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchWellSection(id: string): Promise<WellboreSection> {
  const res = await fetch(`${API_BASE}/domain/sections/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateWellSection(id: string, data: Partial<WellboreSection>): Promise<WellboreSection> {
  const res = await fetch(`${API_BASE}/domain/sections/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteWellSection(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/domain/sections/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function createWellSection(data: Partial<WellboreSection>): Promise<WellboreSection> {
  const res = await fetch(`${API_BASE}/domain/sections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchDailyReports(wellId = ''): Promise<DailyReport[]> {
  const suffix = wellId ? `?well_id=${encodeURIComponent(wellId)}` : ''
  const res = await fetch(`${API_BASE}/domain/reports${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createDailyReport(data: Partial<DailyReport>): Promise<DailyReport> {
  const res = await fetch(`${API_BASE}/domain/reports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchDailyReport(id: string): Promise<DailyReport> {
  const res = await fetch(`${API_BASE}/domain/reports/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateDailyReport(id: string, data: Partial<DailyReport>): Promise<DailyReport> {
  const res = await fetch(`${API_BASE}/domain/reports/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteDailyReport(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/domain/reports/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function fetchDrillingParams(wellId = ''): Promise<DrillingParam[]> {
  const suffix = wellId ? `?well_id=${encodeURIComponent(wellId)}` : ''
  const res = await fetch(`${API_BASE}/domain/params${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createDrillingParam(data: Partial<DrillingParam>): Promise<DrillingParam> {
  const res = await fetch(`${API_BASE}/domain/params`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchDrillingParam(id: string): Promise<DrillingParam> {
  const res = await fetch(`${API_BASE}/domain/params/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateDrillingParam(id: string, data: Partial<DrillingParam>): Promise<DrillingParam> {
  const res = await fetch(`${API_BASE}/domain/params/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteDrillingParam(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/domain/params/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function fetchLasFiles(wellId = ''): Promise<LasFile[]> {
  const suffix = wellId ? `?well_id=${encodeURIComponent(wellId)}` : ''
  const res = await fetch(`${API_BASE}/domain/las-files${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createLasFile(data: Partial<LasFile>): Promise<LasFile> {
  const res = await fetch(`${API_BASE}/domain/las-files`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchLasFile(id: string): Promise<LasFile> {
  const res = await fetch(`${API_BASE}/domain/las-files/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateLasFile(id: string, data: Partial<LasFile>): Promise<LasFile> {
  const res = await fetch(`${API_BASE}/domain/las-files/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteLasFile(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/domain/las-files/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function importLasFile(data: { well_id: string; path: string; filename?: string }): Promise<LasFile> {
  const res = await fetch(`${API_BASE}/domain/las/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function uploadLasFile(data: { well_id: string; file: File; filename?: string }): Promise<LasFile> {
  const form = new FormData()
  form.set('well_id', data.well_id)
  form.set('file', data.file)
  if (data.filename) form.set('filename', data.filename)
  const res = await fetch(`${API_BASE}/domain/las/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchArtifacts(kind = '', wellId = '', agentId = ''): Promise<{ artifacts: ArtifactInfo[] }> {
  const params = new URLSearchParams()
  if (kind) params.set('kind', kind)
  if (wellId) params.set('well_id', wellId)
  if (agentId) params.set('agent_id', agentId)
  const qs = params.toString()
  const res = await fetch(`${API_BASE}/files/artifacts${qs ? `?${qs}` : ''}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteArtifact(kind: ArtifactInfo['kind'], filename: string): Promise<{ deleted: string; kind: string }> {
  const res = await fetch(`${API_BASE}/files/artifacts/${kind}/${encodeURIComponent(filename)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface ChatResult {
  thread_id: string
  trace_id: string
  run_id: string
  response: string
  todos: unknown[]
  message_count: number
  interrupted: boolean
  agent_id: string
  execution_ref: ExecutionRef | null
  payload: Record<string, unknown> | null
}

export interface ExecutionRef {
  agent_id: string
  thread_id: string
  checkpoint_ns: string
  interrupt_id: string
  interrupt_type: string
}

export interface ChatSessionSummary {
  thread_id: string
  agent_id: string
  title: string
  message_count: number
  updated_at: string
  last_trace_id: string
  last_run_id: string
  archived?: boolean
  archived_at?: string
}

export interface ChatSessionDetail {
  thread_id: string
  agent_id: string
  messages: ChatMessage[]
  updated_at: string
  last_trace_id: string
  last_run_id: string
  archived?: boolean
  archived_at?: string
}

export async function fetchAttachmentRecord(agentId: string, attachmentId: string): Promise<AttachmentRecordDto> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments/${encodeURIComponent(attachmentId)}`, {
    headers: consoleAuthHeaders(),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function listAgentAttachments(agentId: string): Promise<{ attachments: AttachmentRecordDto[] }> {
  const res = await fetch(`${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments`, {
    headers: consoleAuthHeaders(),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function uploadAgentAttachment(
  agentId: string,
  file: File,
  relativePath: string,
  onProgress?: (progress: number) => void,
  signal?: AbortSignal,
): Promise<AttachmentRecordDto> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments`)
    const token = localStorage.getItem(CONSOLE_TOKEN_KEY)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as AttachmentRecordDto)
        return
      }
      reject(new Error(xhr.responseText || `上传失败 (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('上传网络错误'))
    xhr.onabort = () => reject(new Error('上传已取消'))
    signal?.addEventListener('abort', () => xhr.abort())
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('relative_path', relativePath === file.name ? '' : relativePath)
    xhr.send(form)
  })
}

export async function retryAgentAttachment(agentId: string, attachmentId: string): Promise<AttachmentRecordDto> {
  const res = await fetch(
    `${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments/${encodeURIComponent(attachmentId)}/retry`,
    { method: 'POST', headers: consoleAuthHeaders() },
  )
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function cancelAgentAttachment(agentId: string, attachmentId: string): Promise<AttachmentRecordDto> {
  const res = await fetch(
    `${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments/${encodeURIComponent(attachmentId)}/cancel`,
    { method: 'POST', headers: consoleAuthHeaders() },
  )
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteAgentAttachment(agentId: string, attachmentId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/agents/${encodeURIComponent(agentId)}/attachments/${encodeURIComponent(attachmentId)}`,
    { method: 'DELETE', headers: consoleAuthHeaders() },
  )
  if (!res.ok) throw new Error(await res.text())
}

export async function sendChat(
  message: string,
  threadId?: string,
  agentId?: string,
  source = 'user',
  lang?: string,
  extras?: Omit<ChatRequestOptions, 'message' | 'threadId' | 'agentId' | 'source' | 'lang'>,
): Promise<ChatResult> {
  const res = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(lang ? { 'Accept-Language': lang } : {}),
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
      agent_id: agentId,
      source,
      lang,
      attachments: extras?.attachments ?? [],
      attachment_ids: extras?.attachment_ids ?? [],
      provider: extras?.provider,
      model: extras?.model,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchChatSessions(
  q = '',
  limit = 50,
  options?: { includeArchived?: boolean; archivedOnly?: boolean },
): Promise<{ sessions: ChatSessionSummary[] }> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  if (options?.includeArchived) params.set('include_archived', 'true')
  if (options?.archivedOnly) params.set('archived_only', 'true')
  const res = await fetch(`${API_BASE}/agent/sessions?${params.toString()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchChatSession(threadId: string): Promise<ChatSessionDetail> {
  const res = await fetch(`${API_BASE}/agent/sessions/${threadId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function exportChatSession(threadId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/agent/sessions/${threadId}/export`)
  if (!res.ok) throw new Error(await res.text())
  return res.text()
}

export async function archiveChatSession(
  threadId: string,
): Promise<{ thread_id: string; archived: boolean; archived_at: string }> {
  const res = await fetch(`${API_BASE}/agent/sessions/${threadId}/archive`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function unarchiveChatSession(
  threadId: string,
): Promise<{ thread_id: string; archived: boolean; archived_at: string }> {
  const res = await fetch(`${API_BASE}/agent/sessions/${threadId}/unarchive`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteChatSession(threadId: string): Promise<{ deleted: string }> {
  const res = await fetch(`${API_BASE}/agent/sessions/${threadId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function confirmPlan(executionRef: ExecutionRef, decision: string, editedTodos?: string[]) {
  const res = await fetch(`${API_BASE}/agent/plan/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ execution_ref: executionRef, decision, edited_todos: editedTodos }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTasks(status?: string): Promise<Task[]> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
  const res = await fetch(`${API_BASE}/tasks${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createTask(title: string, prompt: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, prompt, auto_run: true }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function runTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks/${taskId}/run`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function cancelTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks/${taskId}/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTools(): Promise<{ tools: ToolInfo[] }> {
  const res = await fetch(`${API_BASE}/agent/tools`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTrace(traceId: string): Promise<TraceEvent[]> {
  const res = await fetch(`${API_BASE}/agent/trace/${traceId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchTraceTimeline(traceId: string): Promise<TraceTimeline> {
  const res = await fetch(`${API_BASE}/monitor/trace/${traceId}/timeline`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/monitor/stats`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface MonitorHealth {
  status: string
  ready: boolean
  agent_ready: boolean
  checkpoint: {
    status: string
    backend: string
    persistent: boolean
    supports_restart_resume: boolean
    warning: string
    sqlite_path: string
    open_agent_savers: number
    error: string
  }
}

export async function fetchMonitorHealth(): Promise<MonitorHealth> {
  const res = await fetch(`${API_BASE}/monitor/health`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchRecentEvents(limit = 50): Promise<TraceEvent[]> {
  const res = await fetch(`${API_BASE}/monitor/events?limit=${limit}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- MCP tools -----
export interface McpServerStatus {
  name: string
  configured: boolean
  connected: boolean
  config: Record<string, unknown>
}

export interface McpToolDetail {
  name: string
  description: string
  source: string
  args_schema: Record<string, unknown> | null
}

export interface McpReloadResult {
  status: string
  tools: number
  mcp_tools: number
  servers: McpServerStatus[]
  mcp_tool_details: McpToolDetail[]
}

export async function fetchMcpServers(): Promise<{ servers: McpServerStatus[] }> {
  const res = await fetch(`${API_BASE}/tools/mcp/servers`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchMcpTools(): Promise<{ tools: McpToolDetail[] }> {
  const res = await fetch(`${API_BASE}/tools/mcp/tools`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function reloadMcp(): Promise<McpReloadResult> {
  const res = await fetch(`${API_BASE}/tools/mcp/reload`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Agents (multi-workspace) -----
export interface AgentInfo {
  agent_id: string
  root: string
  created_at: string
  loaded: boolean
  skills_count: number
  config: Record<string, unknown>
}

export interface AgentFileInfo {
  path: string
  size: number
  modified_at: string
}

export interface AgentHistoryItem {
  type: 'task' | 'session'
  id: string
  title: string
  status: string
  thread_id: string
  trace_id: string
  run_id: string
  updated_at: string
  match_source: string
}

export async function fetchAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch(`${API_BASE}/agents`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchAgent(agentId: string): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents/${agentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchAgentFiles(agentId: string): Promise<{ agent_id: string; root: string; files: AgentFileInfo[] }> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/files`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchAgentHistory(agentId: string): Promise<{ agent_id: string; history: AgentHistoryItem[] }> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/history`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createAgent(agentId: string): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, config: {} }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteAgent(
  agentId: string,
  options?: { purge?: boolean },
): Promise<{ deleted: string; purged: boolean; checkpoint_retained: boolean; detail: string }> {
  const qs = options?.purge ? '?purge=true' : ''
  const res = await fetch(`${API_BASE}/agents/${agentId}${qs}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Skills -----
export interface SkillInfo {
  name: string
  description: string
  path: string
  source: string
  enabled: boolean
  languages: string[]
  metadata: Record<string, unknown>
}

export interface SkillFileInfo {
  path: string
  size: number
  is_manifest: boolean
}

export interface SkillScanFinding {
  file: string
  line: number
  category: string
  snippet: string
}

export interface SkillDetail {
  info: SkillInfo
  files: SkillFileInfo[]
  scan: { safe: boolean; findings: SkillScanFinding[] }
}

export async function fetchSkills(agentId = 'default'): Promise<{ pool: SkillInfo[]; workspace: SkillInfo[] }> {
  const res = await fetch(`${API_BASE}/skills?agent_id=${agentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function installSkill(name: string, sourceDir: string, overwrite = false): Promise<SkillInfo> {
  const res = await fetch(`${API_BASE}/skills/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, source_dir: sourceDir, overwrite }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchSkillDetail(
  scope: 'pool' | 'workspace',
  name: string,
  agentId = 'default',
): Promise<SkillDetail> {
  const res = await fetch(`${API_BASE}/skills/${scope}/${name}?agent_id=${agentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchSkillFile(
  scope: 'pool' | 'workspace',
  name: string,
  path = 'SKILL.md',
  agentId = 'default',
): Promise<{ path: string; content: string }> {
  const params = new URLSearchParams({ path, agent_id: agentId })
  const res = await fetch(`${API_BASE}/skills/${scope}/${name}/file?${params.toString()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateSkillFile(
  scope: 'pool' | 'workspace',
  name: string,
  path: string,
  content: string,
  agentId = 'default',
): Promise<{ path: string; info: SkillInfo }> {
  const res = await fetch(`${API_BASE}/skills/${scope}/${name}/file?agent_id=${agentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteSkill(scope: 'pool' | 'workspace', name: string, agentId = 'default') {
  const res = await fetch(`${API_BASE}/skills/${scope}/${name}?agent_id=${agentId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchSkillScanReport(
  scope: 'pool' | 'workspace',
  name: string,
  agentId = 'default',
): Promise<{ safe: boolean; findings: SkillScanFinding[] }> {
  const res = await fetch(`${API_BASE}/skills/${scope}/${name}/scan-report?agent_id=${agentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function setSkillEnabled(name: string, enabled: boolean, agentId = 'default') {
  const res = await fetch(`${API_BASE}/skills/${name}/enable?agent_id=${agentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function addSkillToWorkspace(name: string, agentId = 'default') {
  const res = await fetch(`${API_BASE}/skills/${name}/add-to-workspace?agent_id=${agentId}`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function scanSkill(path: string): Promise<{ safe: boolean; findings: unknown[] }> {
  const res = await fetch(`${API_BASE}/skills/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Providers -----
export interface ProviderInfo {
  name: string
  display_name: string
  configured: boolean
  default_model: string
  requires_api_key: boolean
}

export interface ModelInfo {
  name: string
  provider: string
  context_window: number | null
  max_output_tokens?: number | null
  supports_tools: boolean | null
  supports_vision: boolean | null
  capabilities?: Record<'vision' | 'tools' | 'audio_input' | 'audio_output' | 'structured_output' | 'is_local', 'true' | 'false' | 'unknown'>
  capability_sources?: Record<string, string>
  pricing?: {
    input_per_million?: number | null
    output_per_million?: number | null
  }
  metadata?: Record<string, unknown>
}

export interface RunMetricsSummary {
  trace_id: string
  run_id: string
  agent_id?: string
  provider?: string | null
  model?: string | null
  status?: string
  time_to_first_token_ms?: number | null
  total_duration_ms?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  estimated_cost?: number | null
  cost_currency?: string | null
  cost_is_estimate?: boolean
  graph_cache_hit?: boolean | null
  attachment_count?: number
  retrieval_hits?: number
}

export async function fetchRunMetrics(traceId: string): Promise<RunMetricsSummary> {
  const res = await fetch(`${API_BASE}/agent/runs/metrics/${encodeURIComponent(traceId)}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface ProviderConfig {
  name: string
  api_key_configured: boolean
  base_url: string
  is_default: boolean
  default_model: string
}

export interface DefaultProviderConfig {
  provider: string
  model: string
}

export async function fetchProviders(): Promise<{ providers: ProviderInfo[] }> {
  const res = await fetch(`${API_BASE}/providers`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchDefaultProviderConfig(): Promise<DefaultProviderConfig> {
  const res = await fetch(`${API_BASE}/providers/config`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateDefaultProvider(provider: string, model: string): Promise<DefaultProviderConfig> {
  const res = await fetch(`${API_BASE}/providers/default`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchProviderConfig(name: string): Promise<ProviderConfig> {
  const res = await fetch(`${API_BASE}/providers/${name}/config`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateProviderConfig(
  name: string,
  cfg: { api_key?: string; base_url?: string },
): Promise<ProviderConfig> {
  const res = await fetch(`${API_BASE}/providers/${name}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchProviderModels(name: string): Promise<{ models: ModelInfo[] }> {
  const res = await fetch(`${API_BASE}/providers/${name}/models`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function checkProvider(name: string): Promise<{ provider: string; connected: boolean; detail: string }> {
  const res = await fetch(`${API_BASE}/providers/${name}/check`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Cron & heartbeat -----
export interface CronJob {
  id: string
  name: string
  cron: string
  prompt: string
  channel: string
  chat_id: string
  agent_id: string
  enabled: boolean
  created_at: string
  last_run: string
  last_status: string
  last_error: string
  run_count: number
}

export interface CronRunRecord {
  id: string
  job_id: string
  job_name: string
  status: string
  started_at: string
  finished_at: string
  trace_id: string
  run_id: string
  error: string
}

export interface HeartbeatConfig {
  enabled: boolean
  interval_minutes: number
  prompt: string
  last_channel: string
}

export async function fetchCronJobs(): Promise<{ jobs: CronJob[] }> {
  const res = await fetch(`${API_BASE}/tasks/cron`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createCronJob(job: Partial<CronJob>): Promise<CronJob> {
  const res = await fetch(`${API_BASE}/tasks/cron`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteCronJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tasks/cron/${jobId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function updateCronJob(jobId: string, job: Partial<CronJob>): Promise<CronJob> {
  const res = await fetch(`${API_BASE}/tasks/cron/${jobId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function setCronEnabled(jobId: string, enabled: boolean): Promise<CronJob> {
  const res = await fetch(`${API_BASE}/tasks/cron/${jobId}/enable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function triggerCronJob(jobId: string): Promise<CronRunRecord> {
  const res = await fetch(`${API_BASE}/tasks/cron/${jobId}/trigger`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchCronHistory(jobId = '', limit = 100): Promise<{ history: CronRunRecord[] }> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (jobId) params.set('job_id', jobId)
  const res = await fetch(`${API_BASE}/tasks/cron/history?${params.toString()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchHeartbeat(): Promise<HeartbeatConfig> {
  const res = await fetch(`${API_BASE}/tasks/heartbeat`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateHeartbeat(cfg: Partial<HeartbeatConfig>): Promise<HeartbeatConfig> {
  const res = await fetch(`${API_BASE}/tasks/heartbeat`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Gateway channels -----
export interface GatewayChannelStatus {
  name: string
  configured: boolean
  queue_depth: number
  running: boolean
  consumer_running: boolean
  render_style: string
}

export interface GatewayMessageRecord {
  id: string
  platform: string
  status: string
  detail: string
  message_id: string
  chat_id: string
  user_id: string
  user_name: string
  content: string
  task_id: string
  trace_id: string
  created_at: string
}

export interface GatewayAccessPolicy {
  allowed_users: string[]
}

export interface GatewayAccessControl {
  channels: Record<string, GatewayAccessPolicy>
}

export async function fetchGatewayStatus(): Promise<{ channels: GatewayChannelStatus[] }> {
  const res = await fetch(`${API_BASE}/gateway/status`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchGatewayAccessControl(): Promise<GatewayAccessControl> {
  const res = await fetch(`${API_BASE}/gateway/access-control`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateGatewayAccessControl(data: GatewayAccessControl): Promise<GatewayAccessControl> {
  const res = await fetch(`${API_BASE}/gateway/access-control`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchGatewayMessages(
  platform = '',
  status = '',
  limit = 100,
): Promise<{ messages: GatewayMessageRecord[] }> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (platform) params.set('platform', platform)
  if (status) params.set('status', status)
  const res = await fetch(`${API_BASE}/gateway/messages?${params.toString()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function retryGatewayMessage(recordId: string): Promise<{ retried: string }> {
  const res = await fetch(`${API_BASE}/gateway/messages/${recordId}/retry`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Security / approvals -----
export interface ApprovalRequest {
  id: string
  tool: string
  args: Record<string, unknown>
  findings: { severity: string; category: string; message: string; guardian: string }[]
  thread_id: string
  execution_ref: ExecutionRef | null
  status: string
  decision: string
  error: string
  created_at: string
  updated_at: string
}

export async function fetchApprovals(): Promise<{ pending: ApprovalRequest[] }> {
  const res = await fetch(`${API_BASE}/security/approvals`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchApprovalHistory(): Promise<{ approvals: ApprovalRequest[] }> {
  const res = await fetch(`${API_BASE}/security/approvals/history`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function resumeApproval(approvalId: string, executionRef: ExecutionRef, decision: string) {
  const res = await fetch(`${API_BASE}/security/approvals/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_id: approvalId, execution_ref: executionRef, decision }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchGuardConfig(): Promise<{ enabled: boolean; level: string }> {
  const res = await fetch(`${API_BASE}/security/config`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function updateGuardConfig(level: string): Promise<{ enabled: boolean; level: string }> {
  const res = await fetch(`${API_BASE}/security/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ----- Plugins & commands -----
export interface PluginInfo {
  name: string
  version: string
  type: string
  description: string
  path: string
  enabled: boolean
  loaded: boolean
  tools: string[]
  error: string
}

export interface PluginScanFinding {
  file: string
  line: number
  category: string
  snippet: string
}

export interface PluginDetail extends PluginInfo {
  manifest: Record<string, unknown>
  scan?: { safe: boolean; findings: PluginScanFinding[] }
}

export async function fetchPlugins(): Promise<{ plugins: PluginInfo[] }> {
  const res = await fetch(`${API_BASE}/plugins`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchPluginDetail(name: string): Promise<PluginDetail> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function installPlugin(name: string, sourceDir: string, overwrite = false): Promise<PluginInfo> {
  const res = await fetch(`${API_BASE}/plugins/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, source_dir: sourceDir, overwrite }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function setPluginEnabled(name: string, enabled: boolean): Promise<PluginInfo> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function reloadPlugins(): Promise<{ reloaded: number }> {
  const res = await fetch(`${API_BASE}/plugins/reload`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchPluginScanReport(
  name: string,
): Promise<{ safe: boolean; findings: PluginScanFinding[] }> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}/scan-report`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function scanPlugin(path: string): Promise<{ safe: boolean; findings: PluginScanFinding[] }> {
  const res = await fetch(`${API_BASE}/plugins/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deletePlugin(name: string): Promise<{ deleted: string }> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface CommandInfo {
  name: string
  description: string
  aliases: string[]
}

export async function fetchCommands(): Promise<{ commands: CommandInfo[] }> {
  const res = await fetch(`${API_BASE}/commands`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

