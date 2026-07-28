import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import {
  archiveKnowledgeBase,
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  fetchKnowledgeDocuments,
  removeKnowledgeDocument,
  restoreKnowledgeBase,
  retryKnowledgeDocument,
  uploadKnowledgeDocuments,
  type KnowledgeBaseDto,
  type KnowledgeDocumentDto,
} from '../services/api'
import { formatBytes } from '../utils/attachments'
import KnowledgeSnippetPreview from './KnowledgeSnippetPreview'

interface Props {
  agentId: string
}

function statusLabel(status: string) {
  if (status === 'active') return '活跃'
  if (status === 'archived') return '已归档'
  return status
}

function docStatusLabel(status: string) {
  const map: Record<string, string> = {
    ready: '就绪',
    parsing: '解析中',
    failed: '失败',
    uploaded: '已上传',
    uploading: '上传中',
  }
  return map[status] ?? status
}

export default function KnowledgeBasePage({ agentId }: Props) {
  const [items, setItems] = useState<KnowledgeBaseDto[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [documents, setDocuments] = useState<KnowledgeDocumentDto[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newName, setNewName] = useState('')
  const [preview, setPreview] = useState<{
    kbId: string
    docId: string
    chunkId: string
    title: string
  } | null>(null)

  const selected = items.find(item => item.knowledge_base_id === selectedId) ?? null

  const loadKbs = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetchKnowledgeBases(agentId, { q: query, status: statusFilter || undefined })
      setItems(res.knowledge_bases)
      if (!selectedId && res.knowledge_bases.length > 0) {
        setSelectedId(res.knowledge_bases[0].knowledge_base_id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [agentId, query, statusFilter, selectedId])

  const loadDocs = useCallback(async (kbId: string) => {
    if (!kbId) return
    try {
      const res = await fetchKnowledgeDocuments(agentId, kbId)
      setDocuments(res.documents)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [agentId])

  useEffect(() => { void loadKbs() }, [loadKbs])
  useEffect(() => { if (selectedId) void loadDocs(selectedId) }, [selectedId, loadDocs])

  const handleCreate = async () => {
    if (!newName.trim()) return
    await createKnowledgeBase(agentId, { name: newName.trim() })
    setNewName('')
    await loadKbs()
  }

  const handleUpload = async (files: FileList | null) => {
    if (!selectedId || !files?.length) return
    await uploadKnowledgeDocuments(agentId, selectedId, Array.from(files))
    await loadDocs(selectedId)
    await loadKbs()
  }

  const handleRetry = async (doc: KnowledgeDocumentDto) => {
    await retryKnowledgeDocument(agentId, selectedId, doc.document_id)
    await loadDocs(selectedId)
  }

  const handleRemove = async (doc: KnowledgeDocumentDto) => {
    if (!window.confirm(`确认移除文档「${doc.filename}」？`)) return
    await removeKnowledgeDocument(agentId, selectedId, doc.document_id)
    await loadDocs(selectedId)
    await loadKbs()
  }

  return (
    <div className="agent-workspace-page knowledge-base-page">
      <div className="agent-list-panel route-card">
        <div className="route-card-header">
          <h2><BookOpen size={18} /> 知识库</h2>
          <button type="button" className="mgr-btn compact" onClick={() => void loadKbs()} aria-label="刷新">
            <RefreshCw size={14} />
          </button>
        </div>
        <div className="mgr-form">
          <input
            type="search"
            placeholder="搜索知识库…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="搜索知识库"
          />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} aria-label="状态筛选">
            <option value="">全部状态</option>
            <option value="active">活跃</option>
            <option value="archived">已归档</option>
          </select>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              placeholder="新库名称"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              aria-label="新库名称"
            />
            <button type="button" className="mgr-btn primary-action" onClick={() => void handleCreate()}>
              <Plus size={14} /> 创建
            </button>
          </div>
        </div>
        {error && <p className="detail-action-error" role="alert">{error}</p>}
        <ul className="mgr-list">
          {items.map(item => (
            <li key={item.knowledge_base_id}>
              <button
                type="button"
                className={`mgr-item ${selectedId === item.knowledge_base_id ? 'active' : ''}`}
                onClick={() => setSelectedId(item.knowledge_base_id)}
              >
                <div className="mgr-item-main">
                  <strong>{item.name}</strong>
                  <span className="pill">{statusLabel(item.status)}</span>
                  <span>{item.document_count} 文档 · {formatBytes(item.total_size)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        {!loading && items.length === 0 && <p className="empty-hint">暂无知识库，请先创建。</p>}
      </div>

      <div className="agent-detail-panel route-card">
        {!selected ? (
          <p className="empty-hint">选择或创建一个知识库。</p>
        ) : (
          <>
            <div className="route-card-header">
              <h2>{selected.name}</h2>
              <div style={{ display: 'flex', gap: 8 }}>
                {selected.status === 'active' && (
                  <button type="button" className="mgr-btn secondary" onClick={() => void archiveKnowledgeBase(agentId, selected.knowledge_base_id).then(loadKbs)}>
                    归档
                  </button>
                )}
                {selected.status === 'archived' && (
                  <button type="button" className="mgr-btn secondary" onClick={() => void restoreKnowledgeBase(agentId, selected.knowledge_base_id).then(loadKbs)}>
                    恢复
                  </button>
                )}
                <button
                  type="button"
                  className="mgr-btn danger"
                  onClick={() => {
                    if (!window.confirm('删除后可恢复；确认删除？')) return
                    void deleteKnowledgeBase(agentId, selected.knowledge_base_id).then(loadKbs)
                  }}
                >
                  <Trash2 size={14} /> 删除
                </button>
              </div>
            </div>
            <p className="empty-hint">{selected.description || '暂无说明'}</p>
            <label className="mgr-btn secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <Upload size={14} /> 上传文档
              <input
                type="file"
                multiple
                hidden
                onChange={e => void handleUpload(e.target.files)}
              />
            </label>
            <ul className="mgr-list" style={{ marginTop: 12 }}>
              {documents.map(doc => (
                <li key={doc.document_id} className="mgr-item">
                  <div className="mgr-item-main">
                    <strong>{doc.relative_path || doc.filename}</strong>
                    <span className="pill">{docStatusLabel(doc.status)}</span>
                    <span>{formatBytes(doc.size)} · {String(doc.summary?.chunk_count ?? 0)} 块</span>
                    {doc.error_summary && <span className="detail-action-error">{doc.error_summary}</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {doc.status === 'failed' && (
                      <button type="button" className="mgr-btn compact" onClick={() => void handleRetry(doc)}>重试</button>
                    )}
                    {doc.status === 'ready' && (
                      <button
                        type="button"
                        className="mgr-btn compact"
                        onClick={() => setPreview({
                          kbId: selected.knowledge_base_id,
                          docId: doc.document_id,
                          chunkId: `${doc.document_id}-c0000`,
                          title: doc.filename,
                        })}
                      >
                        预览
                      </button>
                    )}
                    <button type="button" className="mgr-btn compact danger" onClick={() => void handleRemove(doc)}>移除</button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {preview && (
        <KnowledgeSnippetPreview
          agentId={agentId}
          kbId={preview.kbId}
          docId={preview.docId}
          chunkId={preview.chunkId}
          title={preview.title}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  )
}
