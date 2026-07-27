import { useCallback, useEffect, useState } from 'react'
import { Brain, Download, RefreshCw, Trash2 } from 'lucide-react'
import {
  approveMemory,
  bulkDeleteMemories,
  createMemory,
  deleteMemory,
  exportMemories,
  fetchMemories,
  fetchMemoryHealth,
  rejectMemory,
  updateMemory,
  type MemoryRecordDto,
} from '../services/api'

interface Props {
  agentId: string
}

export default function MemoryManager({ agentId }: Props) {
  const [items, setItems] = useState<MemoryRecordDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [editor, setEditor] = useState<MemoryRecordDto | null>(null)
  const [editorContent, setEditorContent] = useState('')
  const [newContent, setNewContent] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [list, healthRes] = await Promise.all([
        fetchMemories(agentId, { q: query, scope, status, page, pageSize: 20 }),
        fetchMemoryHealth(),
      ])
      setItems(list.items)
      setTotal(list.total)
      setHealth(healthRes.health)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [agentId, query, scope, status, page])

  useEffect(() => { void load() }, [load])

  const handleCreate = async () => {
    if (!newContent.trim()) return
    await createMemory({ agentId, content: newContent.trim() })
    setNewContent('')
    await load()
  }

  const handleSave = async () => {
    if (!editor) return
    await updateMemory(agentId, editor.id, { content: editorContent })
    setEditor(null)
    await load()
  }

  const handleDelete = async (item: MemoryRecordDto) => {
    if (!window.confirm(`确认删除记忆「${item.summary || item.id}」？`)) return
    await deleteMemory(agentId, item.id)
    await load()
  }

  const handleBulkDeletePending = async () => {
    if (!window.confirm('确认批量删除所有待审核记忆？')) return
    await bulkDeleteMemories({ agentId, status: 'pending' })
    await load()
  }

  const handleExport = async () => {
    const data = await exportMemories(agentId)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `boetclaw-memories-${agentId}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const disabled = health?.status === 'disabled'

  return (
    <div role="region" aria-label="长期记忆管理">
      <div className="mgr-section-title">
        <Brain size={14} /> 长期记忆
      </div>
      {disabled && (
        <div className="empty-hint">
          {health?.status === 'disabled'
            ? '当前记忆后端未启用。可在环境变量中将 MEMORY_BACKEND 设为 sqlite 后重启服务。'
            : '记忆存储异常，请检查服务健康状态。'}
        </div>
      )}
      {!disabled && (
        <>
          <div className="memory-toolbar">
            <input placeholder="搜索记忆" value={query} onChange={e => setQuery(e.target.value)} aria-label="搜索记忆" />
            <select value={scope} onChange={e => setScope(e.target.value)} aria-label="作用域过滤">
              <option value="">全部作用域</option>
              <option value="agent">Agent 私有</option>
              <option value="thread">线程私有</option>
            </select>
            <select value={status} onChange={e => setStatus(e.target.value)} aria-label="状态过滤">
              <option value="">全部状态</option>
              <option value="active">已保存</option>
              <option value="pending">待审核</option>
              <option value="rejected">已拒绝</option>
            </select>
            <button type="button" className="mgr-btn secondary" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={14} /> 刷新
            </button>
            <button type="button" className="mgr-btn secondary" onClick={() => void handleExport()}>
              <Download size={14} /> 导出
            </button>
          </div>
          <div className="memory-create-row">
            <textarea
              placeholder="手动新增一条长期记忆…"
              value={newContent}
              onChange={e => setNewContent(e.target.value)}
              rows={2}
            />
            <button type="button" className="mgr-btn primary" onClick={() => void handleCreate()}>保存</button>
          </div>
          {error && <div className="detail-action-error">{error}</div>}
          {loading && items.length === 0 && <div className="empty-hint">正在加载记忆…</div>}
          {!loading && items.length === 0 && <div className="empty-hint">暂无匹配记忆。</div>}
          <div className="memory-list">
            {items.map(item => (
              <div className="memory-item" key={item.id}>
                <div className="memory-item-head">
                  <strong>{item.summary || item.content.slice(0, 80)}</strong>
                  <span className="pill">{item.status}</span>
                  <span className="pill">{item.scope}</span>
                </div>
                <p className="memory-item-meta mono">
                  {item.source_type}
                  {item.source_thread ? ` · thread ${item.source_thread.slice(0, 8)}` : ''}
                  {item.use_count ? ` · 使用 ${item.use_count} 次` : ''}
                </p>
                <div className="memory-item-actions">
                  {item.status === 'pending' && (
                    <>
                      <button type="button" className="mgr-btn primary" onClick={() => void approveMemory(agentId, item.id).then(load)}>批准</button>
                      <button type="button" className="mgr-btn secondary" onClick={() => void rejectMemory(agentId, item.id).then(load)}>拒绝</button>
                    </>
                  )}
                  <button type="button" className="mgr-btn secondary" onClick={() => { setEditor(item); setEditorContent(item.content) }}>编辑</button>
                  <button type="button" className="mgr-btn danger" onClick={() => void handleDelete(item)}>
                    <Trash2 size={14} /> 删除
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="memory-pagination">
            <button type="button" className="mgr-btn secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span className="mono">第 {page} 页 · 共 {total} 条</span>
            <button type="button" className="mgr-btn secondary" disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}>下一页</button>
            <button type="button" className="mgr-btn danger" onClick={() => void handleBulkDeletePending()}>批量清理待审核</button>
          </div>
        </>
      )}
      {editor && (
        <div className="memory-editor-overlay" onClick={() => setEditor(null)}>
          <div className="memory-editor" onClick={e => e.stopPropagation()}>
            <h4>编辑记忆</h4>
            <textarea value={editorContent} onChange={e => setEditorContent(e.target.value)} rows={6} />
            <div className="memory-item-actions">
              <button type="button" className="mgr-btn primary" onClick={() => void handleSave()}>保存</button>
              <button type="button" className="mgr-btn secondary" onClick={() => setEditor(null)}>取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
