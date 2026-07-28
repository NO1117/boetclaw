import { useEffect, useState } from 'react'
import { BookOpen } from 'lucide-react'
import { fetchKnowledgeBases, fetchKnowledgeBindings, type KnowledgeBaseDto } from '../services/api'

export type KBSelectionMode = 'default' | 'explicit' | 'disabled'

interface Props {
  agentId: string
  mode: KBSelectionMode
  selectedIds: string[]
  onChange: (mode: KBSelectionMode, ids: string[]) => void
}

export default function KnowledgeBaseSelector({ agentId, mode, selectedIds, onChange }: Props) {
  const [kbs, setKbs] = useState<KnowledgeBaseDto[]>([])
  const [defaultIds, setDefaultIds] = useState<string[]>([])

  useEffect(() => {
    void (async () => {
      try {
        const [kbRes, bindRes] = await Promise.all([
          fetchKnowledgeBases(agentId, { status: 'active' }),
          fetchKnowledgeBindings(agentId),
        ])
        setKbs(kbRes.knowledge_bases)
        const defaults = bindRes.bindings
          .filter(b => b.enabled_by_default)
          .map(b => b.knowledge_base_id)
        setDefaultIds(defaults)
      } catch {
        setKbs([])
        setDefaultIds([])
      }
    })()
  }, [agentId])

  if (kbs.length === 0) return null

  const effectiveLabel = mode === 'default'
    ? `默认 (${defaultIds.length})`
    : mode === 'disabled'
      ? '已关闭'
      : `已选 ${selectedIds.length}`

  return (
    <div className="attachment-chip knowledge-base-selector" aria-label="知识库选择">
      <BookOpen size={14} />
      <select
        value={mode === 'default' ? '__default__' : mode === 'disabled' ? '__none__' : selectedIds[0] ?? '__pick__'}
        onChange={e => {
          const v = e.target.value
          if (v === '__default__') onChange('default', [])
          else if (v === '__none__') onChange('disabled', [])
          else onChange('explicit', [v])
        }}
        aria-label="选择知识库"
      >
        <option value="__default__">知识库：{effectiveLabel}</option>
        <option value="__none__">关闭知识库检索</option>
        {kbs.map(kb => (
          <option key={kb.knowledge_base_id} value={kb.knowledge_base_id}>{kb.name}</option>
        ))}
      </select>
    </div>
  )
}

export function knowledgeBaseIdsForRequest(
  mode: KBSelectionMode,
  selectedIds: string[],
): string[] | null | undefined {
  if (mode === 'default') return undefined
  if (mode === 'disabled') return []
  return selectedIds
}
