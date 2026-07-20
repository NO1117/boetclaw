import { useState } from 'react'
import { X, Settings, BookOpen, Cpu, Clock, Puzzle } from 'lucide-react'
import SkillsManager from './SkillsManager'
import ProviderSettings from './ProviderSettings'
import CronManager from './CronManager'
import PluginsManager from './PluginsManager'
import './Console.css'

interface Props {
  agentId: string
  onClose: () => void
}

type Tab = 'skills' | 'providers' | 'cron' | 'plugins'

const TABS: { id: Tab; label: string; icon: typeof BookOpen }[] = [
  { id: 'skills', label: '技能', icon: BookOpen },
  { id: 'providers', label: '模型', icon: Cpu },
  { id: 'cron', label: '定时/心跳', icon: Clock },
  { id: 'plugins', label: '插件', icon: Puzzle },
]

export default function ConsoleModal({ agentId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('skills')

  return (
    <div className="console-overlay" onClick={onClose}>
      <div className="console-modal" onClick={e => e.stopPropagation()}>
        <div className="console-header">
          <h2><Settings size={16} /> 管理控制台</h2>
          <button className="mgr-btn secondary" onClick={onClose}><X size={14} /></button>
        </div>
        <div className="console-tabs">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`console-tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <t.icon size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              {t.label}
            </button>
          ))}
        </div>
        <div className="console-body">
          {tab === 'skills' && <SkillsManager agentId={agentId} />}
          {tab === 'providers' && <ProviderSettings />}
          {tab === 'cron' && <CronManager />}
          {tab === 'plugins' && <PluginsManager />}
        </div>
      </div>
    </div>
  )
}
