import { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, Plus } from 'lucide-react'
import { fetchAgents, createAgent, type AgentInfo } from '../services/api'

interface Props {
  currentAgent: string
  onSwitch: (agentId: string) => void
}

export default function AgentSwitcher({ currentAgent, onSwitch }: Props) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [open, setOpen] = useState(false)
  const [newId, setNewId] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const load = async () => {
    try {
      const data = await fetchAgents()
      setAgents(data.agents)
    } catch { /* ignore */ }
  }

  useEffect(() => { void load() }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleCreate = async () => {
    const id = newId.trim()
    if (!id) return
    try {
      await createAgent(id)
      setNewId('')
      await load()
      onSwitch(id)
      setOpen(false)
    } catch { /* ignore */ }
  }

  return (
    <div className="agent-switcher" ref={ref}>
      <button className="agent-switcher-btn" onClick={() => setOpen(o => !o)}>
        <Bot size={14} /> {currentAgent} <ChevronDown size={13} />
      </button>
      {open && (
        <div className="agent-menu">
          {agents.map(a => (
            <button
              key={a.agent_id}
              className={`agent-menu-item ${a.agent_id === currentAgent ? 'active' : ''}`}
              onClick={() => { onSwitch(a.agent_id); setOpen(false) }}
            >
              <span>{a.agent_id}</span>
              <span className={`pill ${a.loaded ? 'ok' : 'off'}`}>{a.loaded ? '就绪' : '未载'}</span>
            </button>
          ))}
          <div className="agent-create">
            <input
              placeholder="新智能体 ID"
              value={newId}
              onChange={e => setNewId(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void handleCreate() }}
            />
            <button className="mgr-btn" onClick={() => void handleCreate()}><Plus size={13} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
