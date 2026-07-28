import { useCallback, useEffect, useState } from 'react'
import {
  bindKnowledgeBase,
  fetchKnowledgeBases,
  fetchKnowledgeBindings,
  unbindKnowledgeBase,
  updateKnowledgeBinding,
  type KnowledgeBaseDto,
  type KnowledgeBindingDto,
} from '../services/api'

interface Props {
  agentId: string
}

export default function AgentKnowledgeBindings({ agentId }: Props) {
  const [kbs, setKbs] = useState<KnowledgeBaseDto[]>([])
  const [bindings, setBindings] = useState<KnowledgeBindingDto[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [kbRes, bindRes] = await Promise.all([
        fetchKnowledgeBases(agentId),
        fetchKnowledgeBindings(agentId),
      ])
      setKbs(kbRes.knowledge_bases.filter(k => k.status === 'active'))
      setBindings(bindRes.bindings)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => { void load() }, [load])

  const isBound = (kbId: string) => bindings.some(b => b.knowledge_base_id === kbId)
  const bindingOf = (kbId: string) => bindings.find(b => b.knowledge_base_id === kbId)

  const toggleBind = async (kb: KnowledgeBaseDto) => {
    if (isBound(kb.knowledge_base_id)) {
      await unbindKnowledgeBase(agentId, kb.knowledge_base_id)
    } else {
      await bindKnowledgeBase(agentId, kb.knowledge_base_id, true)
    }
    await load()
  }

  const toggleDefault = async (kbId: string) => {
    const current = bindingOf(kbId)
    if (!current) return
    await updateKnowledgeBinding(agentId, kbId, !current.enabled_by_default)
    await load()
  }

  return (
    <div className="mgr-form">
      <h3 className="mgr-section-title">知识库绑定</h3>
      {error && <p className="detail-action-error" role="alert">{error}</p>}
      {loading && <p className="page-state loading">加载中…</p>}
      <ul className="mgr-list">
        {kbs.map(kb => {
          const bound = isBound(kb.knowledge_base_id)
          const binding = bindingOf(kb.knowledge_base_id)
          return (
            <li key={kb.knowledge_base_id} className="mgr-item">
              <div className="mgr-item-main">
                <strong>{kb.name}</strong>
                <span>{kb.document_count} 文档</span>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button type="button" className="mgr-btn compact" onClick={() => void toggleBind(kb)}>
                  {bound ? '解绑' : '绑定'}
                </button>
                {bound && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <input
                      type="checkbox"
                      checked={binding?.enabled_by_default ?? false}
                      onChange={() => void toggleDefault(kb.knowledge_base_id)}
                    />
                    默认启用
                  </label>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {!loading && kbs.length === 0 && (
        <p className="empty-hint">当前 Agent 尚无活跃知识库，请先在知识库页面创建。</p>
      )}
    </div>
  )
}
