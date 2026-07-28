import { expect, type BrowserContext, type Page, type Route } from '@playwright/test'

export type StreamMode = 'echo' | 'plan' | 'approval' | 'hang'

export interface FakeBackendOptions {
  /** When true, console login gate is enabled (CONSOLE_PASSWORD path). */
  loginRequired?: boolean
  consolePassword?: string
  /** Default chat/stream behaviour for unmatched agent prompts. */
  streamMode?: StreamMode
}

export interface ExecutionRef {
  agent_id: string
  thread_id: string
  checkpoint_ns: string
  interrupt_id: string
  interrupt_type: string
}

export interface FakeStore {
  loginRequired: boolean
  consolePassword: string
  authenticated: boolean
  token: string
  streamMode: StreamMode
  agents: Array<{ agent_id: string; loaded: boolean }>
  wells: Array<Record<string, unknown>>
  reports: Array<Record<string, unknown>>
  params: Array<Record<string, unknown>>
  tasks: Array<Record<string, unknown>>
  taskAttempts: Record<string, Array<Record<string, unknown>>>
  taskEvents: Record<string, Array<Record<string, unknown>>>
  taskQueuePaused: boolean
  taskEventSeq: number
  approvals: Array<Record<string, unknown>>
  lastChatBody: Record<string, unknown> | null
  lastPlanConfirm: Record<string, unknown> | null
  lastApprovalResume: Record<string, unknown> | null
  lastCancelRun: Record<string, unknown> | null
  attachments: Record<string, Record<string, unknown>>
  knowledgeBases: Record<string, Record<string, unknown>>
  kbDocuments: Record<string, Record<string, unknown>>
  kbBindings: Record<string, Array<Record<string, unknown>>>
  lastVoiceTranscription: Record<string, unknown> | null
  lastVoiceSpeech: Record<string, unknown> | null
  lastVoiceCapabilities: Record<string, unknown> | null
  memories: Record<string, Record<string, unknown>>
  memoryHealth: Record<string, unknown>
  agentProfiles: Record<string, Record<string, unknown>>
  agentProfileVersions: Record<string, Array<Record<string, unknown>>>
  providerConnections: Record<string, Record<string, unknown>>
  hangReleases: Array<() => void>
  releaseHangStreams: () => void
  reset: () => void
}

function nowIso() {
  return new Date().toISOString()
}

function sse(envelopes: unknown[]) {
  return envelopes.map(e => {
    const envelope = e as Record<string, unknown>
    const event = String(envelope.event ?? 'message')
    return `event: ${event}\ndata: ${JSON.stringify(e)}\n\n`
  }).join('')
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function defaultProfile(agentId: string) {
  return {
    display_name: agentId === 'default' ? '默认智能体' : agentId,
    description: '',
    avatar_color: '#6366f1',
    system_prompt: '',
    provider: '',
    model: '',
    temperature: null,
    max_output_tokens: null,
    tool_policy: 'inherit',
    tool_allowlist: [] as string[],
    memory_mode: 'inherit',
    default_language: 'zh',
    enabled: true,
  }
}

function profileResponse(agentId: string, store: FakeStore, revision = 1) {
  const configured = {
    ...defaultProfile(agentId),
    ...(store.agentProfiles[agentId] ?? {}),
  }
  return {
    agent_id: agentId,
    configured,
    effective: {
      ...configured,
      provider: configured.provider || 'fake',
      model: configured.model || 'fake-model',
      model_string: `${configured.provider || 'fake'}:${configured.model || 'fake-model'}`,
      revision,
    },
    revision,
    apply_state: {
      revision,
      status: 'applied',
      applied_at: nowIso(),
      error_summary: '',
    },
  }
}

export function createFakeStore(options: FakeBackendOptions = {}): FakeStore {
  const hangReleases: Array<() => void> = []
  const store: FakeStore = {
    loginRequired: options.loginRequired ?? false,
    consolePassword: options.consolePassword ?? 'e2e-console-pass',
    authenticated: !(options.loginRequired ?? false),
    token: 'e2e-console-token',
    streamMode: options.streamMode ?? 'echo',
    agents: [
      { agent_id: 'default', loaded: true },
      { agent_id: 'workspace-a', loaded: true },
    ],
    wells: [],
    reports: [],
    params: [],
    tasks: [],
    taskAttempts: {},
    taskEvents: {},
    taskQueuePaused: false,
    taskEventSeq: 0,
    approvals: [],
    lastChatBody: null,
    lastPlanConfirm: null,
    lastApprovalResume: null,
    lastCancelRun: null,
    attachments: {},
    knowledgeBases: {},
    kbDocuments: {},
    kbBindings: {},
    lastVoiceTranscription: null,
    lastVoiceSpeech: null,
    lastVoiceCapabilities: null,
    memories: {},
    agentProfiles: {
      default: defaultProfile('default'),
      'workspace-a': defaultProfile('workspace-a'),
    },
    agentProfileVersions: {
      default: [{ revision: 1, created_at: nowIso(), changed_fields: ['created'], operator: 'system' }],
      'workspace-a': [{ revision: 1, created_at: nowIso(), changed_fields: ['created'], operator: 'system' }],
    },
    providerConnections: {
      'conn-fake-default': {
        id: 'conn-fake-default',
        provider_type: 'fake',
        display_name: 'Fake 默认连接',
        base_url: '',
        credential_id: null,
        credential_configured: true,
        credential_source: 'none',
        credential_fingerprint: '',
        default_model: 'fake-model',
        enabled: true,
        timeout_seconds: 30,
        revision: 1,
        is_default: true,
        created_at: nowIso(),
        updated_at: nowIso(),
        last_check: null,
      },
    },
    memoryHealth: {
      status: 'ready',
      backend: 'sqlite',
      persistent: true,
      schema_version: 1,
      fts_enabled: true,
      writable: true,
      mode: 'review',
      error: '',
    },
    hangReleases,
    releaseHangStreams() {
      while (hangReleases.length) hangReleases.pop()?.()
    },
    reset() {
      store.wells = []
      store.reports = []
      store.params = []
      store.tasks = []
      store.taskAttempts = {}
      store.taskEvents = {}
      store.taskQueuePaused = false
      store.taskEventSeq = 0
      store.approvals = []
      store.lastChatBody = null
      store.lastPlanConfirm = null
      store.lastApprovalResume = null
      store.lastCancelRun = null
      store.attachments = {}
      store.knowledgeBases = {}
      store.kbDocuments = {}
      store.kbBindings = {}
      store.lastVoiceTranscription = null
      store.lastVoiceSpeech = null
      store.lastVoiceCapabilities = null
      store.memories = {}
      store.agentProfiles = {
        default: defaultProfile('default'),
        'workspace-a': defaultProfile('workspace-a'),
      }
      store.agentProfileVersions = {
        default: [{ revision: 1, created_at: nowIso(), changed_fields: ['created'], operator: 'system' }],
        'workspace-a': [{ revision: 1, created_at: nowIso(), changed_fields: ['created'], operator: 'system' }],
      }
      store.providerConnections = {
        'conn-fake-default': {
          id: 'conn-fake-default',
          provider_type: 'fake',
          display_name: 'Fake 默认连接',
          base_url: '',
          credential_id: null,
          credential_configured: true,
          credential_source: 'none',
          credential_fingerprint: '',
          default_model: 'fake-model',
          enabled: true,
          timeout_seconds: 30,
          revision: 1,
          is_default: true,
          created_at: nowIso(),
          updated_at: nowIso(),
          last_check: null,
        },
      }
      store.authenticated = !store.loginRequired
      store.releaseHangStreams()
    },
  }
  return store
}

function planRef(agentId: string, threadId: string): ExecutionRef {
  return {
    agent_id: agentId,
    thread_id: threadId,
    checkpoint_ns: '',
    interrupt_id: `plan-${agentId}-${threadId}`,
    interrupt_type: 'plan_confirm',
  }
}

function approvalRef(agentId: string, threadId: string): ExecutionRef {
  return {
    agent_id: agentId,
    thread_id: threadId,
    checkpoint_ns: '',
    interrupt_id: `approval-${agentId}-${threadId}`,
    interrupt_type: 'tool_approval',
  }
}

export async function installFakeBackend(
  page: Page,
  options: FakeBackendOptions = {},
  context?: BrowserContext,
) {
  const store = createFakeStore(options)
  const router = context ?? page

  await router.route('**/api/v1/**', async route => {
    try {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/\/+$/, '')
    const method = request.method()

    // ----- auth -----
    if (path.endsWith('/auth/status')) {
      return json(route, {
        login_required: store.loginRequired,
        authenticated: store.authenticated,
        ttl_minutes: 480,
      })
    }
    if (path.endsWith('/auth/login') && method === 'POST') {
      const body = request.postDataJSON() as { password?: string }
      if (!store.loginRequired) {
        return json(route, { login_required: false, authenticated: true, token: '' })
      }
      if (body.password !== store.consolePassword) {
        return json(route, { detail: 'invalid password' }, 401)
      }
      store.authenticated = true
      return json(route, {
        login_required: true,
        authenticated: true,
        token: store.token,
        ttl_minutes: 480,
      })
    }
    if (path.endsWith('/auth/logout') && method === 'POST') {
      store.authenticated = false
      return json(route, { ok: true })
    }

    // ----- agents / sessions / monitor stubs -----
    if (path.endsWith('/agents') && method === 'GET') {
      return json(route, {
        agents: store.agents.map(a => ({
          ...a,
          root: `/workspace/agents/${a.agent_id}`,
          created_at: nowIso(),
          skills_count: 0,
          config: store.agentProfiles[a.agent_id] ?? {},
          profile: {
            display_name: (store.agentProfiles[a.agent_id] as { display_name?: string } | undefined)?.display_name ?? a.agent_id,
            enabled: true,
            revision: store.agentProfileVersions[a.agent_id]?.at(-1)?.revision ?? 1,
          },
        })),
      })
    }
    if (path.endsWith('/agents') && method === 'POST') {
      const body = request.postDataJSON() as { agent_id?: string; profile?: Record<string, unknown> | null }
      const agentId = String(body.agent_id ?? '')
      if (!store.agents.some(a => a.agent_id === agentId)) {
        store.agents.push({ agent_id: agentId, loaded: false })
        store.agentProfiles[agentId] = {
          ...defaultProfile(agentId),
          ...(body.profile ?? {}),
        }
        store.agentProfileVersions[agentId] = [{ revision: 1, created_at: nowIso(), changed_fields: ['created'], operator: 'system' }]
      }
      return json(route, {
        agent_id: agentId,
        root: `/workspace/agents/${agentId}`,
        created_at: nowIso(),
        loaded: false,
        skills_count: 0,
        config: store.agentProfiles[agentId] ?? {},
        profile: { display_name: agentId, enabled: true, revision: 1 },
      })
    }
    const profileValidateMatch = path.match(/\/agents\/([^/]+)\/profile\/validate$/)
    if (profileValidateMatch && method === 'POST') {
      const agentId = decodeURIComponent(profileValidateMatch[1])
      const body = request.postDataJSON() as { profile?: Record<string, unknown> }
      const prompt = String(body.profile?.system_prompt ?? '')
      if (prompt.includes('api_key') || prompt.includes('sk-')) {
        return json(route, { valid: false, errors: ['检测到疑似密钥'], warnings: [] })
      }
      return json(route, { valid: true, errors: [], warnings: [] })
    }
    const profileVersionsMatch = path.match(/\/agents\/([^/]+)\/profile\/versions$/)
    if (profileVersionsMatch && method === 'GET') {
      const agentId = decodeURIComponent(profileVersionsMatch[1])
      const versions = store.agentProfileVersions[agentId] ?? []
      return json(route, { agent_id: agentId, total: versions.length, offset: 0, limit: 20, versions: [...versions].reverse() })
    }
    const profileVersionDetailMatch = path.match(/\/agents\/([^/]+)\/profile\/versions\/(\d+)$/)
    if (profileVersionDetailMatch && method === 'GET') {
      const agentId = decodeURIComponent(profileVersionDetailMatch[1])
      const revision = Number(profileVersionDetailMatch[2])
      return json(route, {
        agent_id: agentId,
        revision,
        record: { revision, created_at: nowIso(), changed_fields: ['display_name'], operator: 'system' },
        snapshot: store.agentProfiles[agentId] ?? defaultProfile(agentId),
        diff_from_current: revision === 1 ? ['display_name'] : [],
      })
    }
    const profileRollbackMatch = path.match(/\/agents\/([^/]+)\/profile\/rollback$/)
    if (profileRollbackMatch && method === 'POST') {
      const agentId = decodeURIComponent(profileRollbackMatch[1])
      const current = profileResponse(agentId, store, (store.agentProfileVersions[agentId]?.length ?? 1) + 1)
      store.agentProfileVersions[agentId] = [...(store.agentProfileVersions[agentId] ?? []), { revision: current.revision, created_at: nowIso(), changed_fields: ['rollback'], operator: 'system' }]
      return json(route, current)
    }
    const profileMatch = path.match(/\/agents\/([^/]+)\/profile$/)
    if (profileMatch && method === 'GET') {
      const agentId = decodeURIComponent(profileMatch[1])
      const revision = store.agentProfileVersions[agentId]?.at(-1)?.revision ?? 1
      return json(route, profileResponse(agentId, store, Number(revision)))
    }
    if (profileMatch && method === 'PUT') {
      const agentId = decodeURIComponent(profileMatch[1])
      const body = request.postDataJSON() as { revision?: number; profile?: Record<string, unknown> }
      const currentRevision = Number(store.agentProfileVersions[agentId]?.at(-1)?.revision ?? 1)
      if (body.revision !== currentRevision) {
        return json(route, { detail: { message: 'revision conflict', expected_revision: body.revision, actual_revision: currentRevision } }, 409)
      }
      store.agentProfiles[agentId] = {
        ...defaultProfile(agentId),
        ...(store.agentProfiles[agentId] ?? {}),
        ...(body.profile ?? {}),
      }
      const nextRevision = currentRevision + 1
      store.agentProfileVersions[agentId] = [...(store.agentProfileVersions[agentId] ?? []), { revision: nextRevision, created_at: nowIso(), changed_fields: Object.keys(body.profile ?? {}), operator: 'api' }]
      return json(route, profileResponse(agentId, store, nextRevision))
    }
    const cloneMatch = path.match(/\/agents\/([^/]+)\/clone$/)
    if (cloneMatch && method === 'POST') {
      const sourceId = decodeURIComponent(cloneMatch[1])
      const body = request.postDataJSON() as { new_agent_id?: string | null }
      const newId = body.new_agent_id || `${sourceId}-copy`
      if (!store.agents.some(a => a.agent_id === newId)) {
        store.agents.push({ agent_id: newId, loaded: false })
        store.agentProfiles[newId] = {
          ...defaultProfile(newId),
          ...(store.agentProfiles[sourceId] ?? {}),
          display_name: `${(store.agentProfiles[sourceId] as { display_name?: string })?.display_name ?? sourceId} (副本)`,
        }
        store.agentProfileVersions[newId] = [{ revision: 1, created_at: nowIso(), changed_fields: ['clone'], operator: 'system' }]
      }
      return json(route, profileResponse(newId, store, 1))
    }
    const exportMatch = path.match(/\/agents\/([^/]+)\/export$/)
    if (exportMatch && method === 'GET') {
      const agentId = decodeURIComponent(exportMatch[1])
      return json(route, {
        export_version: 1,
        exported_at: nowIso(),
        profile: { agent_id: agentId, ...(store.agentProfiles[agentId] ?? defaultProfile(agentId)) },
      })
    }
    if (path.endsWith('/agents/import') && method === 'POST') {
      const body = request.postDataJSON() as { agent_id?: string | null; payload?: { profile?: Record<string, unknown> } }
      const importedId = body.agent_id || String(body.payload?.profile?.agent_id ?? 'imported-agent')
      if (!store.agents.some(a => a.agent_id === importedId)) {
        store.agents.push({ agent_id: importedId, loaded: false })
      }
      store.agentProfiles[importedId] = {
        ...defaultProfile(importedId),
        ...(body.payload?.profile ?? {}),
      }
      store.agentProfileVersions[importedId] = [{ revision: 1, created_at: nowIso(), changed_fields: ['import'], operator: 'system' }]
      return json(route, profileResponse(importedId, store, 1))
    }
    const agentFilesMatch = path.match(/\/agents\/([^/]+)\/files$/)
    if (agentFilesMatch && method === 'GET') {
      const agentId = decodeURIComponent(agentFilesMatch[1])
      return json(route, { agent_id: agentId, root: `/workspace/agents/${agentId}`, files: [] })
    }
    const agentHistoryMatch = path.match(/\/agents\/([^/]+)\/history$/)
    if (agentHistoryMatch && method === 'GET') {
      const agentId = decodeURIComponent(agentHistoryMatch[1])
      return json(route, { agent_id: agentId, history: [] })
    }
    const attachmentCollectionMatch = path.match(/\/agents\/([^/]+)\/attachments$/)
    if (attachmentCollectionMatch && method === 'POST') {
      const agentId = decodeURIComponent(attachmentCollectionMatch[1])
      const attachmentId = `att-${agentId}-${Object.keys(store.attachments).length + 1}`
      const record = {
        attachment_id: attachmentId,
        agent_id: agentId,
        filename: 'fixture.txt',
        relative_path: '',
        mime_type: 'text/plain',
        size: 18,
        kind: 'text',
        status: 'ready',
        scan_status: 'unscanned',
        error_summary: '',
        summary: { chunk_count: 1, searchable: true, char_count: 18, page_count: null, sheet_count: null, slide_count: null },
        created_at: nowIso(),
        updated_at: nowIso(),
        expires_at: nowIso(),
        content: 'fixture citation text',
      }
      store.attachments[attachmentId] = record
      return json(route, { ...record, status: 'uploaded' })
    }
    const attachmentItemMatch = path.match(/\/agents\/([^/]+)\/attachments\/([^/]+)$/)
    if (attachmentItemMatch && method === 'GET') {
      const attachmentId = decodeURIComponent(attachmentItemMatch[2])
      const record = store.attachments[attachmentId]
      if (!record) return json(route, { detail: 'not found' }, 404)
      return json(route, record)
    }

    const kbCollectionMatch = path.match(/\/agents\/([^/]+)\/knowledge-bases$/)
    if (kbCollectionMatch && method === 'GET') {
      const agentId = decodeURIComponent(kbCollectionMatch[1])
      const rows = Object.values(store.knowledgeBases).filter(kb => kb.agent_id === agentId)
      return json(route, { knowledge_bases: rows })
    }
    if (kbCollectionMatch && method === 'POST') {
      const agentId = decodeURIComponent(kbCollectionMatch[1])
      const body = request.postDataJSON() as Record<string, unknown>
      const kbId = `kb-${agentId}-${Object.keys(store.knowledgeBases).length + 1}`
      const record = {
        knowledge_base_id: kbId,
        agent_id: agentId,
        name: String(body.name ?? '知识库'),
        description: String(body.description ?? ''),
        status: 'active',
        document_count: 0,
        total_size: 0,
        revision: 1,
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      store.knowledgeBases[kbId] = record
      return json(route, record)
    }
    const kbItemMatch = path.match(/\/agents\/([^/]+)\/knowledge-bases\/([^/]+)$/)
    if (kbItemMatch && method === 'GET') {
      const kbId = decodeURIComponent(kbItemMatch[2])
      const record = store.knowledgeBases[kbId]
      if (!record) return json(route, { detail: 'not found' }, 404)
      return json(route, record)
    }
    const kbDocsMatch = path.match(/\/agents\/([^/]+)\/knowledge-bases\/([^/]+)\/documents$/)
    if (kbDocsMatch && method === 'GET') {
      const kbId = decodeURIComponent(kbDocsMatch[2])
      const docs = Object.values(store.kbDocuments).filter(d => d.knowledge_base_id === kbId)
      return json(route, { documents: docs })
    }
    const kbUploadMatch = path.match(/\/agents\/([^/]+)\/knowledge-bases\/([^/]+)\/documents\/upload$/)
    if (kbUploadMatch && method === 'POST') {
      const agentId = decodeURIComponent(kbUploadMatch[1])
      const kbId = decodeURIComponent(kbUploadMatch[2])
      const docId = `doc-${kbId}-${Object.keys(store.kbDocuments).length + 1}`
      const record = {
        document_id: docId,
        knowledge_base_id: kbId,
        agent_id: agentId,
        filename: 'fixture-kb.txt',
        relative_path: '',
        mime_type: 'text/plain',
        size: 24,
        kind: 'document',
        status: 'ready',
        scan_status: 'unscanned',
        error_summary: '',
        summary: { chunk_count: 1, searchable: true, char_count: 24 },
        source_attachment_id: '',
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      store.kbDocuments[docId] = record
      const kb = store.knowledgeBases[kbId]
      if (kb) {
        kb.document_count = Number(kb.document_count ?? 0) + 1
        kb.total_size = Number(kb.total_size ?? 0) + 24
      }
      return json(route, { documents: [record] })
    }
    const kbPreviewMatch = path.match(/\/agents\/([^/]+)\/knowledge-bases\/([^/]+)\/documents\/([^/]+)\/preview$/)
    if (kbPreviewMatch && method === 'GET') {
      return json(route, {
        text: 'fixture kb snippet preview text',
        filename: 'fixture-kb.txt',
        location: { section: 'p1' },
        truncated: false,
      })
    }
    const kbBindingsMatch = path.match(/\/agents\/([^/]+)\/knowledge-base-bindings$/)
    if (kbBindingsMatch && method === 'GET') {
      const agentId = decodeURIComponent(kbBindingsMatch[1])
      return json(route, { bindings: store.kbBindings[agentId] ?? [] })
    }
    const kbBindItemMatch = path.match(/\/agents\/([^/]+)\/knowledge-base-bindings\/([^/]+)$/)
    if (kbBindItemMatch && method === 'POST') {
      const agentId = decodeURIComponent(kbBindItemMatch[1])
      const kbId = decodeURIComponent(kbBindItemMatch[2])
      const body = request.postDataJSON() as Record<string, unknown>
      const binding = {
        knowledge_base_id: kbId,
        enabled_by_default: body.enabled_by_default !== false,
        bound_at: nowIso(),
      }
      store.kbBindings[agentId] = [...(store.kbBindings[agentId] ?? []).filter(b => b.knowledge_base_id !== kbId), binding]
      return json(route, binding)
    }
    if (kbBindItemMatch && method === 'PATCH') {
      const agentId = decodeURIComponent(kbBindItemMatch[1])
      const kbId = decodeURIComponent(kbBindItemMatch[2])
      const body = request.postDataJSON() as Record<string, unknown>
      store.kbBindings[agentId] = (store.kbBindings[agentId] ?? []).map(b =>
        b.knowledge_base_id === kbId
          ? { ...b, enabled_by_default: body.enabled_by_default !== false }
          : b,
      )
      const binding = (store.kbBindings[agentId] ?? []).find(b => b.knowledge_base_id === kbId)
      return json(route, binding ?? { knowledge_base_id: kbId, enabled_by_default: true, bound_at: nowIso() })
    }
    if (kbBindItemMatch && method === 'DELETE') {
      const agentId = decodeURIComponent(kbBindItemMatch[1])
      const kbId = decodeURIComponent(kbBindItemMatch[2])
      store.kbBindings[agentId] = (store.kbBindings[agentId] ?? []).filter(b => b.knowledge_base_id !== kbId)
      return json(route, { unbound: true, knowledge_base_id: kbId })
    }
    const agentMatch = path.match(/\/agents\/([^/]+)$/)
    if (agentMatch && method === 'GET') {
      const agentId = decodeURIComponent(agentMatch[1])
      return json(route, {
        agent_id: agentId,
        root: `/workspace/agents/${agentId}`,
        created_at: nowIso(),
        loaded: true,
        skills_count: 0,
        config: store.agentProfiles[agentId] ?? {},
        profile: {
          display_name: (store.agentProfiles[agentId] as { display_name?: string } | undefined)?.display_name ?? agentId,
          enabled: true,
          revision: store.agentProfileVersions[agentId]?.at(-1)?.revision ?? 1,
        },
      })
    }
    if (agentMatch && method === 'DELETE') {
      const agentId = decodeURIComponent(agentMatch[1])
      const purge = url.searchParams.get('purge') === 'true'
      store.agents = store.agents.filter(a => a.agent_id !== agentId)
      return json(route, {
        deleted: agentId,
        purged: purge,
        checkpoint_retained: !purge,
        detail: purge ? 'purged' : 'archived',
      })
    }
    if (path.endsWith('/agent/sessions')) {
      return json(route, { sessions: [] })
    }
    if (path.includes('/monitor/events')) {
      return json(route, [])
    }
    if (path.includes('/monitor/stats')) {
      return json(route, {
        tasks: {},
        trace_events: 0,
        event_types: {},
        events: [],
      })
    }
    if (path.endsWith('/monitor/health')) {
      return json(route, {
        status: 'healthy',
        ready: true,
        agent_ready: true,
        checkpoint: {
          status: 'ready',
          backend: 'sqlite',
          persistent: true,
          supports_restart_resume: true,
          warning: '',
          sqlite_path: '/tmp/checkpoints',
          open_agent_savers: 1,
          error: '',
        },
        memory: store.memoryHealth,
      })
    }

    if (path.endsWith('/memories/health')) {
      return json(route, { health: store.memoryHealth, metrics: { created: Object.keys(store.memories).length } })
    }
    if (path.endsWith('/memories/export') && method === 'GET') {
      const agentId = url.searchParams.get('agent_id') ?? 'default'
      return json(route, {
        agent_id: agentId,
        exported_at: nowIso(),
        memories: Object.values(store.memories).filter(m => m.agent_id === agentId && m.status === 'active'),
      })
    }
    if (path.endsWith('/memories/bulk-delete') && method === 'POST') {
      const body = request.postDataJSON() as { agent_id?: string; status?: string; ids?: string[] }
      const agentId = String(body.agent_id ?? '')
      let deleted = 0
      for (const [id, row] of Object.entries(store.memories)) {
        if (row.agent_id !== agentId) continue
        if (body.status && row.status !== body.status) continue
        if (body.ids?.length && !body.ids.includes(id)) continue
        if (!body.status && !(body.ids?.length)) continue
        delete store.memories[id]
        deleted += 1
      }
      if (!body.status && !(body.ids?.length)) {
        return json(route, { detail: 'bulk delete requires filter' }, 400)
      }
      return json(route, { deleted })
    }
    if (path.endsWith('/memories') && method === 'GET') {
      const agentId = url.searchParams.get('agent_id') ?? 'default'
      const status = url.searchParams.get('status') ?? ''
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const items = Object.values(store.memories).filter(row => {
        if (row.agent_id !== agentId) return false
        if (status && row.status !== status) return false
        if (q && !String(row.summary ?? row.content).toLowerCase().includes(q)) return false
        return row.status !== 'deleted'
      })
      return json(route, { items, total: items.length, page: 1, page_size: 20 })
    }
    if (path.endsWith('/memories') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      const id = `mem-${Object.keys(store.memories).length + 1}`
      const record = {
        id,
        agent_id: String(body.agent_id ?? 'default'),
        scope: String(body.scope ?? 'agent'),
        thread_id: String(body.thread_id ?? ''),
        content: String(body.content ?? ''),
        summary: String(body.content ?? '').slice(0, 80),
        tags: Array.isArray(body.tags) ? body.tags : [],
        source_type: 'manual',
        source_thread: '',
        source_trace: '',
        status: String(body.status ?? 'active'),
        created_at: nowIso(),
        updated_at: nowIso(),
        last_used_at: '',
        use_count: 0,
      }
      store.memories[id] = record
      return json(route, record)
    }
    const memoryItemMatch = path.match(/\/memories\/([^/]+)(?:\/(approve|reject))?$/)
    if (memoryItemMatch) {
      const memoryId = decodeURIComponent(memoryItemMatch[1])
      const action = memoryItemMatch[2]
      const agentId = url.searchParams.get('agent_id') ?? 'default'
      const record = store.memories[memoryId]
      if (!record || record.agent_id !== agentId) return json(route, { detail: 'not found' }, 404)
      if (method === 'GET' && !action) return json(route, record)
      if (method === 'PATCH' && !action) {
        const body = request.postDataJSON() as Record<string, unknown>
        Object.assign(record, body, { updated_at: nowIso() })
        return json(route, record)
      }
      if (method === 'DELETE' && !action) {
        delete store.memories[memoryId]
        return json(route, { deleted: true, memory_id: memoryId })
      }
      if (method === 'POST' && action === 'approve') {
        record.status = 'active'
        return json(route, record)
      }
      if (method === 'POST' && action === 'reject') {
        record.status = 'rejected'
        return json(route, record)
      }
    }
    if (path.includes('/voice/capabilities')) {
      store.lastVoiceCapabilities = { at: nowIso() }
      return json(route, {
        provider: 'fake',
        stt: {
          status: 'configured',
          model: 'fake-stt',
          formats: ['webm', 'wav', 'mp3'],
          max_upload_bytes: 26214400,
          max_duration_seconds: 600,
        },
        tts: {
          status: 'configured',
          model: 'fake-tts',
          voice: 'fake-voice',
          formats: ['mp3'],
          max_text_chars: 4096,
        },
        browser_fallback: true,
      })
    }
    if (path.endsWith('/voice/transcriptions') && method === 'POST') {
      store.lastVoiceTranscription = { at: nowIso() }
      return json(route, {
        text: 'E2E fake transcript',
        language: 'zh',
        duration_seconds: 1.2,
        provider: 'fake',
        model: 'fake-stt',
        trace_id: 'voice-trace-e2e',
        duration_ms: 42,
      })
    }
    if (path.endsWith('/voice/speech') && method === 'POST') {
      store.lastVoiceSpeech = request.postDataJSON() as Record<string, unknown>
      await route.fulfill({
        status: 200,
        contentType: 'audio/mpeg',
        headers: {
          'Cache-Control': 'no-store',
          'X-Voice-Trace-Id': 'voice-tts-e2e',
        },
        body: Buffer.from('FAKE-MP3-E2E'),
      })
      return
    }
    if (path.endsWith('/provider-connections/vault/status')) {
      return json(route, { configured: true, writable: true, credential_count: 0, message: '' })
    }
    if (path.endsWith('/provider-connections/import-env') && method === 'POST') {
      return json(route, { imported_connection_ids: [], count: 0, env_cleanup_required: false, message: '无可导入项' })
    }
    if (path.endsWith('/provider-connections') && method === 'GET') {
      return json(route, { connections: Object.values(store.providerConnections) })
    }
    if (path.endsWith('/provider-connections') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      const id = `conn-e2e-${Object.keys(store.providerConnections).length + 1}`
      const conn = {
        id,
        provider_type: String(body.provider_type ?? 'fake'),
        display_name: String(body.display_name ?? 'E2E 连接'),
        base_url: String(body.base_url ?? ''),
        credential_id: body.api_key ? `cred-${id}` : null,
        credential_configured: Boolean(body.api_key),
        credential_source: body.api_key ? 'vault' : 'none',
        credential_fingerprint: body.api_key ? 'e2e1' : '',
        default_model: String(body.default_model ?? 'fake-model'),
        enabled: body.enabled !== false,
        timeout_seconds: 30,
        revision: 1,
        is_default: false,
        created_at: nowIso(),
        updated_at: nowIso(),
        last_check: null,
      }
      store.providerConnections[id] = conn
      return json(route, { connection: conn })
    }
    const connModelsMatch = path.match(/\/provider-connections\/([^/]+)\/models$/)
    if (connModelsMatch && method === 'GET') {
      return json(route, {
        models: [{
          name: 'fake-model',
          provider: 'fake',
          context_window: 128000,
          supports_tools: true,
          supports_vision: true,
        }],
      })
    }
    const connCheckMatch = path.match(/\/provider-connections\/([^/]+)\/check$/)
    if (connCheckMatch && method === 'POST') {
      const cid = decodeURIComponent(connCheckMatch[1])
      const conn = store.providerConnections[cid]
      if (conn) {
        conn.last_check = {
          connected: true,
          detail: 'ok',
          error_category: '',
          latency_ms: 12,
          model_count: 1,
          checked_at: nowIso(),
        }
      }
      return json(route, {
        connection_id: cid,
        provider_type: 'fake',
        connected: true,
        detail: 'ok',
        latency_ms: 12,
        model_count: 1,
      })
    }
    const connDefaultMatch = path.match(/\/provider-connections\/([^/]+)\/set-default$/)
    if (connDefaultMatch && method === 'POST') {
      const cid = decodeURIComponent(connDefaultMatch[1])
      for (const c of Object.values(store.providerConnections)) c.is_default = false
      if (store.providerConnections[cid]) store.providerConnections[cid].is_default = true
      return json(route, { connection: store.providerConnections[cid] })
    }
    const connItemMatch = path.match(/\/provider-connections\/([^/]+)$/)
    if (connItemMatch) {
      const cid = decodeURIComponent(connItemMatch[1])
      if (method === 'GET') {
        const conn = store.providerConnections[cid]
        if (!conn) return json(route, { detail: 'not found' }, 404)
        return json(route, { connection: conn })
      }
      if (method === 'PUT') {
        const body = request.postDataJSON() as Record<string, unknown>
        const conn = store.providerConnections[cid]
        if (!conn) return json(route, { detail: 'not found' }, 404)
        if (body.display_name) conn.display_name = String(body.display_name)
        if (body.base_url !== undefined) conn.base_url = String(body.base_url)
        if (body.default_model) conn.default_model = String(body.default_model)
        if (body.api_key) {
          conn.credential_configured = true
          conn.credential_source = 'vault'
          conn.credential_fingerprint = 'e2e1'
        }
        conn.revision = Number(conn.revision ?? 1) + 1
        conn.updated_at = nowIso()
        return json(route, { connection: conn })
      }
      if (method === 'DELETE') {
        delete store.providerConnections[cid]
        return json(route, { deleted: true, connection_id: cid })
      }
    }
    if (path.endsWith('/providers/config')) {
      return json(route, { provider: 'fake', model: 'fake-model', connection_id: 'conn-fake-default' })
    }
    if (path.endsWith('/providers') && method === 'GET') {
      return json(route, {
        providers: [{
          name: 'fake',
          display_name: 'Fake Provider',
          configured: true,
          default_model: 'fake-model',
          requires_api_key: false,
        }],
      })
    }
    if (path.endsWith('/providers/fake/models')) {
      return json(route, {
        models: [
          {
            name: 'fake-model',
            provider: 'fake',
            context_window: 128000,
            supports_tools: true,
            supports_vision: true,
            capabilities: {
              vision: 'true',
              tools: 'true',
              audio_input: 'unknown',
              audio_output: 'unknown',
              structured_output: 'true',
              is_local: 'false',
            },
          },
          {
            name: 'text-pro',
            provider: 'fake',
            context_window: 64000,
            supports_tools: true,
            supports_vision: false,
            capabilities: {
              vision: 'false',
              tools: 'true',
              audio_input: 'unknown',
              audio_output: 'unknown',
              structured_output: 'true',
              is_local: 'false',
            },
          },
          {
            name: 'local-llama',
            provider: 'fake',
            context_window: 128000,
            supports_tools: true,
            supports_vision: null,
            capabilities: {
              vision: 'unknown',
              tools: 'true',
              audio_input: 'unknown',
              audio_output: 'unknown',
              structured_output: 'unknown',
              is_local: 'true',
            },
          },
        ],
      })
    }
    const runMetricsMatch = path.match(/\/agent\/runs\/metrics\/([^/]+)$/)
    if (runMetricsMatch && method === 'GET') {
      const traceId = decodeURIComponent(runMetricsMatch[1])
      return json(route, {
        trace_id: traceId,
        run_id: `run-${traceId}`,
        provider: 'fake',
        model: 'fake-model',
        status: 'completed',
        time_to_first_token_ms: 800,
        total_duration_ms: 6400,
        input_tokens: 3842,
        output_tokens: 716,
        total_tokens: 4558,
        estimated_cost: 0.082,
        cost_currency: 'USD',
        cost_is_estimate: true,
        graph_cache_hit: true,
        attachment_count: 1,
        retrieval_hits: 6,
      })
    }
    if (path.endsWith('/skills')) {
      return json(route, { pool: [], workspace: [] })
    }
    if (path.endsWith('/tasks') && method === 'GET') {
      return json(route, store.tasks)
    }
    if (path.includes('/monitor/')) {
      return json(route, { events: [], sequence: [] })
    }
    if (path.endsWith('/agent/tools') || path.endsWith('/tools')) {
      return json(route, { tools: [] })
    }
    if (path.endsWith('/files/artifacts')) {
      return json(route, { artifacts: [] })
    }
    if (path.endsWith('/security/config')) {
      return json(route, { enabled: true, level: 'smart' })
    }
    if (path.endsWith('/security/approvals/history')) {
      return json(route, { approvals: [] })
    }
    if (path.endsWith('/security/approvals') && method === 'GET') {
      return json(route, { pending: store.approvals.filter(a => a.status === 'pending') })
    }
    if (path.endsWith('/security/approvals/resume') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      store.lastApprovalResume = body
      const id = String(body.approval_id ?? '')
      const decision = String(body.decision ?? 'approve')
      store.approvals = store.approvals.map(a =>
        a.id === id
          ? { ...a, status: decision === 'reject' ? 'rejected' : 'approved', decision }
          : a,
      )
      return json(route, { resumed: true, decision, approval_id: id })
    }

    // ----- chat stream (fake provider) -----
    if (path.endsWith('/agent/chat/stream') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      store.lastChatBody = body
      const agentId = String(body.agent_id ?? 'default')
      const threadId = String(body.thread_id || `thread-${agentId}-${Date.now()}`)
      const message = String(body.message ?? '')
      const attachmentCount = Array.isArray(body.attachments) ? body.attachments.length : 0
      const attachmentIdCount = Array.isArray(body.attachment_ids) ? body.attachment_ids.length : 0
      const kbIdCount = Array.isArray(body.knowledge_base_ids) ? body.knowledge_base_ids.length : 0
      const attachmentSuffix =
        attachmentIdCount > 0
          ? `:attachment_ids=${attachmentIdCount}`
          : attachmentCount > 0
            ? `:attachments=${attachmentCount}`
            : ''
      const kbSuffix = kbIdCount > 0 ? `:kb=${kbIdCount}` : ''
      const mode: StreamMode =
        message.startsWith('/plan')
          ? 'plan'
          : message.includes('__approval__')
            ? 'approval'
            : message.includes('__hang__')
              ? 'hang'
              : store.streamMode

      const provider = String(body.provider ?? 'fake')
      const model = String(body.model ?? 'fake-model')
      const hasImageAttachment = Array.isArray(body.attachments)
        && (body.attachments as Array<{ kind?: string; mime_type?: string }>).some(
          a => a.kind === 'image' || String(a.mime_type ?? '').startsWith('image/'),
        )

      if (hasImageAttachment && model === 'text-pro') {
        return json(route, {
          detail: {
            error_code: 'MODEL_INCOMPATIBLE',
            message: '不可选：当前图片需要视觉能力',
            provider,
            model,
            missing_capabilities: ['vision'],
          },
        }, 400)
      }

      const runMetrics = {
        trace_id: `trace-${threadId}`,
        run_id: `run-${threadId}`,
        provider,
        model,
        status: 'completed',
        time_to_first_token_ms: 800,
        total_duration_ms: 6400,
        input_tokens: attachmentIdCount > 0 ? 3842 : null,
        output_tokens: attachmentIdCount > 0 ? 716 : null,
        total_tokens: attachmentIdCount > 0 ? 4558 : null,
        estimated_cost: attachmentIdCount > 0 ? 0.082 : null,
        cost_currency: attachmentIdCount > 0 ? 'USD' : null,
        cost_is_estimate: attachmentIdCount > 0,
        graph_cache_hit: true,
        attachment_count: attachmentIdCount || attachmentCount,
        retrieval_hits: attachmentIdCount > 0 ? 6 : kbIdCount > 0 ? 2 : 0,
      }

      const knowledgeCitations = kbIdCount > 0
        ? [{
            knowledge_base_id: String((body.knowledge_base_ids as string[])[0]),
            knowledge_base_name: 'E2E 知识库',
            document_id: 'doc-e2e',
            document_name: 'fixture-kb.txt',
            chunk_id: 'doc-e2e-c0000',
            location: { section: 'p1' },
            score: 1,
            truncated: false,
            snippet: 'fixture kb snippet',
          }]
        : []

      const memoryContext = {
        mode: 'review',
        backend: 'sqlite',
        persistent: true,
        saved_count: Object.values(store.memories).filter(m => m.agent_id === agentId && m.status === 'active').length,
        used_count: message.includes('__memory_used__') ? 1 : 0,
        pending_count: Object.values(store.memories).filter(m => m.agent_id === agentId && m.status === 'pending').length,
        injected_chars: message.includes('__memory_used__') ? 42 : 0,
        items: message.includes('__memory_used__')
          ? [{ id: 'mem-used', scope: 'agent', summary: '用户偏好中文', source_type: 'manual' }]
          : [],
      }
      const memoryCandidates = message.includes('__memory_candidate__')
        ? [{
            id: 'mem-pending-1',
            summary: '我的偏好是使用 Markdown 输出',
            content: '我的偏好是使用 Markdown 输出',
            scope: 'agent',
            source_type: 'user_chat',
            source_thread: threadId,
            source_trace: `trace-${threadId}`,
          }]
        : []
      const memoryActions = message.includes('请记住')
        ? [{ action: 'remember', success: true, memory_id: 'mem-explicit', message: '已保存到长期记忆' }]
        : []

      if (message.includes('__memory_candidate__')) {
        store.memories['mem-pending-1'] = {
          id: 'mem-pending-1',
          agent_id: agentId,
          scope: 'agent',
          thread_id: '',
          content: '我的偏好是使用 Markdown 输出',
          summary: '我的偏好是使用 Markdown 输出',
          tags: [],
          source_type: 'user_chat',
          source_thread: threadId,
          source_trace: `trace-${threadId}`,
          status: 'pending',
          created_at: nowIso(),
          updated_at: nowIso(),
          last_used_at: '',
          use_count: 0,
        }
      }

      const base = {
        version: '1',
        thread_id: threadId,
        agent_id: agentId,
        trace_id: `trace-${threadId}`,
        run_id: `run-${threadId}`,
      }

      if (mode === 'hang') {
        await new Promise<void>(resolve => {
          store.hangReleases.push(resolve)
        })
        return route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sse([
            {
              ...base,
              event: 'update',
              data: { data: { type: 'message', content: 'still running' } },
            },
            { ...base, event: 'done', data: { response: 'done after hang' } },
          ]),
        })
      }

      if (mode === 'plan') {
        const ref = planRef(agentId, threadId)
        return route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sse([
            {
              ...base,
              event: 'interrupt',
              data: { execution_ref: ref, todos: ['核对井况', '生成报告'] },
            },
            { ...base, event: 'done', data: {} },
          ]),
        })
      }

      if (mode === 'approval') {
        const ref = approvalRef(agentId, threadId)
        const approval = {
          id: `approval-${threadId}`,
          tool: 'write_file',
          args: { path: 'report.md' },
          findings: [
            {
              severity: 'high',
              category: 'write',
              message: '写入需审批',
              guardian: 'path',
            },
          ],
          thread_id: threadId,
          execution_ref: ref,
          status: 'pending',
          decision: '',
          error: '',
          created_at: nowIso(),
          updated_at: nowIso(),
        }
        store.approvals = [approval, ...store.approvals]
        return route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sse([
            {
              ...base,
              event: 'interrupt',
              data: { execution_ref: ref },
            },
            { ...base, event: 'done', data: {} },
          ]),
        })
      }

      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sse([
          {
            ...base,
            event: 'update',
            data: { data: { type: 'message', content: `echo:${agentId}:${message}${attachmentSuffix}${kbSuffix}` } },
          },
          { ...base, event: 'done', data: {
            response: `echo:${agentId}:${message}${attachmentSuffix}${kbSuffix}`,
            run_metrics: runMetrics,
            memory_context: memoryContext,
            memory_candidates: memoryCandidates,
            memory_actions: memoryActions,
            knowledge_citations: knowledgeCitations,
          } },
        ]),
      })
    }

    if (path.endsWith('/agent/runs/cancel') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      store.lastCancelRun = body
      store.releaseHangStreams()
      return json(route, { cancelled: true, detail: 'cancelled' })
    }

    if (path.endsWith('/agent/plan/confirm') && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      store.lastPlanConfirm = body
      const ref = body.execution_ref as ExecutionRef
      expect(ref?.agent_id).toBeTruthy()
      expect(ref?.thread_id).toBeTruthy()
      expect(ref?.interrupt_id).toBeTruthy()
      return json(route, {
        resumed: true,
        response: '计划已继续执行。',
        execution_ref: ref,
      })
    }

    // ----- tasks -----
    if (path.endsWith('/tasks/stats') && method === 'GET') {
      const statusCounts: Record<string, number> = {}
      for (const task of store.tasks) {
        const status = String(task.status || 'pending')
        statusCounts[status] = (statusCounts[status] || 0) + 1
      }
      return json(route, {
        queue_depth: store.tasks.filter(t => ['pending', 'queued', 'scheduled', 'retry_wait'].includes(String(t.status))).length,
        status_counts: statusCounts,
        dead_letter_count: statusCounts.dead_letter || 0,
        retry_total: Object.values(store.taskAttempts).flat().length,
        lease_reclaimed_total: 0,
        paused: store.taskQueuePaused,
      })
    }
    if (path.endsWith('/tasks/queue/control') && method === 'POST') {
      const body = request.postDataJSON() as { paused: boolean }
      store.taskQueuePaused = !!body.paused
      const statusCounts: Record<string, number> = {}
      for (const task of store.tasks) {
        const status = String(task.status || 'pending')
        statusCounts[status] = (statusCounts[status] || 0) + 1
      }
      return json(route, {
        queue_depth: store.tasks.length,
        status_counts: statusCounts,
        dead_letter_count: statusCounts.dead_letter || 0,
        retry_total: 0,
        lease_reclaimed_total: 0,
        paused: store.taskQueuePaused,
      })
    }
    if (path.endsWith('/tasks/list') && method === 'GET') {
      const status = url.searchParams.get('status')
      const q = (url.searchParams.get('q') || '').toLowerCase()
      let tasks = status
        ? store.tasks.filter(t => t.status === status || (status === 'pending' && t.status === 'queued'))
        : store.tasks
      if (q) {
        tasks = tasks.filter(t => JSON.stringify(t).toLowerCase().includes(q))
      }
      return json(route, { items: tasks, next_cursor: null })
    }
    if (path.endsWith('/tasks/events/stream') && method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: ping\ndata: {}\n\n' })
      return
    }
    if (path.endsWith('/tasks') && method === 'GET') {
      const status = url.searchParams.get('status')
      const tasks = status
        ? store.tasks.filter(t => t.status === status || (status === 'pending' && t.status === 'queued'))
        : store.tasks
      return json(route, tasks)
    }
    if (path.endsWith('/tasks') && method === 'POST') {
      const body = request.postDataJSON() as {
        title: string
        prompt: string
        auto_run?: boolean
        scheduled_at?: string
        priority?: number
        idempotency_key?: string
      }
      if (body.idempotency_key) {
        const existing = store.tasks.find(t => t.idempotency_key === body.idempotency_key)
        if (existing) return json(route, existing, 201)
      }
      const scheduled = body.scheduled_at || ''
      const status = scheduled ? 'scheduled' : (body.auto_run === false ? 'pending' : 'running')
      const task = {
        id: `task-${store.tasks.length + 1}`,
        title: body.title,
        prompt: body.prompt,
        status,
        thread_id: `task-thread-${store.tasks.length + 1}`,
        trace_id: `task-trace-${store.tasks.length + 1}`,
        run_id: `task-run-${store.tasks.length + 1}`,
        result: '',
        error: '',
        gateway: '',
        created_at: nowIso(),
        updated_at: nowIso(),
        scheduled_at: scheduled,
        priority: body.priority ?? 0,
        attempt_count: status === 'running' ? 1 : 0,
        max_attempts: 3,
        retry_after: '',
        agent_id: 'default',
        source: 'api',
        revision: 1,
        metadata: {},
        run_snapshot: {},
        idempotency_key: body.idempotency_key || '',
      }
      store.tasks = [task, ...store.tasks]
      store.taskEvents[task.id as string] = [{
        id: ++store.taskEventSeq,
        task_id: task.id,
        event_type: 'created',
        payload: { status },
        created_at: nowIso(),
      }]
      if (status === 'running') {
        store.taskAttempts[task.id as string] = [{
          id: 1,
          task_id: task.id,
          attempt_number: 1,
          status: 'running',
          started_at: nowIso(),
          finished_at: '',
          duration_ms: 0,
        }]
      }
      return json(route, task, 201)
    }
    const taskMatch = path.match(/\/tasks\/([^/]+)(?:\/(cancel|run|requeue|retry|attempts|events))?$/)
    if (taskMatch) {
      const taskId = decodeURIComponent(taskMatch[1])
      const action = taskMatch[2]
      const task = store.tasks.find(t => t.id === taskId)
      if (!task) return json(route, { detail: 'Task not found' }, 404)
      if (action === 'attempts' && method === 'GET') {
        return json(route, store.taskAttempts[taskId] || [])
      }
      if (action === 'events' && method === 'GET') {
        return json(route, store.taskEvents[taskId] || [])
      }
      if ((action === 'requeue' || action === 'retry') && method === 'POST') {
        task.status = 'pending'
        task.updated_at = nowIso()
        return json(route, task)
      }
      if (action === 'cancel' && method === 'POST') {
        task.status = 'cancelled'
        task.updated_at = nowIso()
        return json(route, task)
      }
      if (action === 'run' && method === 'POST') {
        task.status = 'running'
        task.updated_at = nowIso()
        return json(route, task)
      }
      if (method === 'GET') return json(route, task)
    }

    // ----- domain -----
    if (path.endsWith('/domain/wells') && method === 'GET') {
      return json(route, store.wells)
    }
    if (path.endsWith('/domain/wells') && method === 'POST') {
      const input = request.postDataJSON() as Record<string, unknown>
      const well = {
        id: `well-${store.wells.length + 1}`,
        name: input.name,
        field: input.field ?? '',
        operator: input.operator ?? '',
        location: input.location ?? '',
        status: input.status ?? 'planned',
        metadata: {},
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      store.wells = [...store.wells, well]
      return json(route, well)
    }
    const wellMatch = path.match(/\/domain\/wells\/([^/]+)$/)
    if (wellMatch) {
      const id = decodeURIComponent(wellMatch[1])
      const idx = store.wells.findIndex(w => w.id === id)
      if (idx < 0) return json(route, { detail: 'Well not found' }, 404)
      if (method === 'GET') return json(route, store.wells[idx])
      if (method === 'PUT') {
        const input = request.postDataJSON() as Record<string, unknown>
        store.wells[idx] = { ...store.wells[idx], ...input, id, updated_at: nowIso() }
        return json(route, store.wells[idx])
      }
      if (method === 'DELETE') {
        store.wells = store.wells.filter(w => w.id !== id)
        return json(route, { ok: true })
      }
    }

    if (path.endsWith('/domain/reports') && method === 'GET') {
      const wellId = url.searchParams.get('well_id')
      const rows = wellId
        ? store.reports.filter(r => r.well_id === wellId)
        : store.reports
      return json(route, rows)
    }
    if (path.endsWith('/domain/reports') && method === 'POST') {
      const input = request.postDataJSON() as Record<string, unknown>
      const report = {
        id: `report-${store.reports.length + 1}`,
        ...input,
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      store.reports = [...store.reports, report]
      return json(route, report)
    }
    const reportMatch = path.match(/\/domain\/reports\/([^/]+)$/)
    if (reportMatch) {
      const id = decodeURIComponent(reportMatch[1])
      const idx = store.reports.findIndex(r => r.id === id)
      if (idx < 0) return json(route, { detail: 'not found' }, 404)
      if (method === 'PUT') {
        const input = request.postDataJSON() as Record<string, unknown>
        store.reports[idx] = { ...store.reports[idx], ...input, id, updated_at: nowIso() }
        return json(route, store.reports[idx])
      }
      if (method === 'DELETE') {
        store.reports = store.reports.filter(r => r.id !== id)
        return json(route, { ok: true })
      }
      return json(route, store.reports[idx])
    }

    if (path.endsWith('/domain/params') && method === 'GET') {
      const wellId = url.searchParams.get('well_id')
      const rows = wellId
        ? store.params.filter(r => r.well_id === wellId)
        : store.params
      return json(route, rows)
    }
    if (path.endsWith('/domain/params') && method === 'POST') {
      const input = request.postDataJSON() as Record<string, unknown>
      const row = {
        id: `param-${store.params.length + 1}`,
        ...input,
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      store.params = [...store.params, row]
      return json(route, row)
    }

    if (/\/domain\/(sections|las-files)$/.test(path)) {
      return json(route, [])
    }

    // Default empty JSON for remaining console probes.
    return json(route, {})
    } catch (error) {
      return json(route, { detail: error instanceof Error ? error.message : String(error) }, 500)
    }
  })

  return store
}
