import { useEffect, useState } from 'react'
import { BookOpen, ShieldCheck, ShieldAlert, RefreshCw, Trash2 } from 'lucide-react'
import {
  deleteSkill,
  fetchSkillDetail,
  fetchSkillFile,
  fetchSkills,
  fetchSkillScanReport,
  installSkill,
  setSkillEnabled,
  addSkillToWorkspace,
  scanSkill,
  updateSkillFile,
  type SkillDetail,
  type SkillScanFinding,
  type SkillInfo,
} from '../services/api'

interface Props {
  agentId: string
}

export default function SkillsManager({ agentId }: Props) {
  const [pool, setPool] = useState<SkillInfo[]>([])
  const [workspace, setWorkspace] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [scanResult, setScanResult] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<{ scope: 'pool' | 'workspace'; name: string } | null>(null)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [filePath, setFilePath] = useState('SKILL.md')
  const [fileContent, setFileContent] = useState('')
  const [findings, setFindings] = useState<SkillScanFinding[]>([])
  const [installName, setInstallName] = useState('')
  const [sourceDir, setSourceDir] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchSkills(agentId)
      setPool(data.pool)
      setWorkspace(data.workspace)
    } catch (e) { setError(String(e)) }
    setLoading(false)
  }

  useEffect(() => { void load() }, [agentId])

  const handleToggle = async (name: string, enabled: boolean) => {
    await setSkillEnabled(name, enabled, agentId)
    await load()
  }

  const handleAdd = async (name: string) => {
    await addSkillToWorkspace(name, agentId)
    await load()
  }

  const handleScan = async (path: string, name: string) => {
    const result = await scanSkill(path)
    setScanResult(prev => ({ ...prev, [name]: result.safe }))
    setFindings(result.findings as SkillScanFinding[])
  }

  const openDetail = async (scope: 'pool' | 'workspace', name: string) => {
    setError('')
    setSelected({ scope, name })
    const data = await fetchSkillDetail(scope, name, agentId)
    setDetail(data)
    setFindings(data.scan.findings)
    const first = data.files.find(f => f.is_manifest)?.path || data.files[0]?.path || 'SKILL.md'
    setFilePath(first)
    const file = await fetchSkillFile(scope, name, first, agentId)
    setFileContent(file.content)
  }

  const handleSelectFile = async (path: string) => {
    if (!selected) return
    setFilePath(path)
    const file = await fetchSkillFile(selected.scope, selected.name, path, agentId)
    setFileContent(file.content)
  }

  const handleSaveFile = async () => {
    if (!selected) return
    setError('')
    await updateSkillFile(selected.scope, selected.name, filePath, fileContent, agentId)
    await openDetail(selected.scope, selected.name)
    await load()
  }

  const handleDelete = async (scope: 'pool' | 'workspace', name: string) => {
    if (!window.confirm(`确认删除 ${scope} 技能 ${name}？`)) return
    await deleteSkill(scope, name, agentId)
    if (selected?.scope === scope && selected.name === name) {
      setSelected(null)
      setDetail(null)
      setFileContent('')
    }
    await load()
  }

  const handleInstall = async () => {
    if (!installName.trim() || !sourceDir.trim()) return
    setError('')
    await installSkill(installName.trim(), sourceDir.trim(), overwrite)
    setInstallName('')
    setSourceDir('')
    setOverwrite(false)
    await load()
  }

  const handleReport = async (scope: 'pool' | 'workspace', name: string) => {
    const report = await fetchSkillScanReport(scope, name, agentId)
    setFindings(report.findings)
  }

  return (
    <div>
      <div className="mgr-section-title">安装技能到全局池</div>
      <div className="mgr-form skill-install-form">
        <input placeholder="技能名称" value={installName} onChange={e => setInstallName(e.target.value)} />
        <input placeholder="源目录（包含 SKILL.md）" value={sourceDir} onChange={e => setSourceDir(e.target.value)} />
        <label className="inline-check">
          <input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} />
          覆盖已存在
        </label>
        <button className="mgr-btn" onClick={() => void handleInstall()}>安装</button>
      </div>
      {error && <div className="detail-action-error">{error}</div>}

      <div className="mgr-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>工作区技能（{agentId}）</span>
        <button className="mgr-btn secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={12} /> 刷新
        </button>
      </div>
      <div className="mgr-list">
        {workspace.length === 0 && <div className="empty-hint">尚未添加工作区技能，可从下方技能池添加。</div>}
        {workspace.map(s => (
          <div className="mgr-item" key={s.name}>
            <div className="mgr-item-main">
              <h4>{s.name}</h4>
              <p>{s.description || '—'}</p>
            </div>
            <div className="mgr-actions">
              <span className={`pill ${s.enabled ? 'ok' : 'off'}`}>{s.enabled ? '启用' : '停用'}</span>
              <button className="mgr-btn secondary" onClick={() => void openDetail('workspace', s.name)}>详情</button>
              <button className="mgr-btn secondary" onClick={() => void handleReport('workspace', s.name)}>扫描详情</button>
              <div
                className={`switch ${s.enabled ? 'on' : ''}`}
                role="switch"
                aria-checked={s.enabled}
                onClick={() => void handleToggle(s.name, !s.enabled)}
              />
              <button className="mgr-btn danger" onClick={() => void handleDelete('workspace', s.name)}>
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="mgr-section-title">技能池（全局共享）</div>
      <div className="mgr-list">
        {pool.map(s => (
          <div className="mgr-item" key={s.name}>
            <div className="mgr-item-main">
              <h4><BookOpen size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />{s.name}</h4>
              <p>{s.description || '—'}</p>
            </div>
            <div className="mgr-actions">
              {scanResult[s.name] !== undefined && (
                <span className={`pill ${scanResult[s.name] ? 'ok' : 'off'}`}>
                  {scanResult[s.name] ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                  {scanResult[s.name] ? ' 安全' : ' 风险'}
                </span>
              )}
              <button className="mgr-btn secondary" onClick={() => void handleScan(s.path, s.name)}>扫描</button>
              <button className="mgr-btn secondary" onClick={() => void openDetail('pool', s.name)}>详情</button>
              <button className="mgr-btn" onClick={() => void handleAdd(s.name)}>添加</button>
              <button className="mgr-btn danger" onClick={() => void handleDelete('pool', s.name)}>
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {detail && selected && (
        <>
          <div className="mgr-section-title">{selected.scope} · {detail.info.name} · 详情与文件</div>
          <div className="skill-detail-grid">
            <div className="mgr-list">
              <div className="mgr-item">
                <div className="mgr-item-main">
                  <h4>{detail.info.name}</h4>
                  <p>{detail.info.description || '—'}</p>
                  <p>{detail.info.path}</p>
                </div>
                <span className={`pill ${detail.scan.safe ? 'ok' : 'off'}`}>
                  {detail.scan.safe ? '扫描通过' : `${detail.scan.findings.length} 个风险`}
                </span>
              </div>
              {detail.files.map(file => (
                <button
                  key={file.path}
                  className={`route-list-item ${file.path === filePath ? 'active' : ''}`}
                  onClick={() => void handleSelectFile(file.path)}
                >
                  <div>
                    <strong>{file.path}</strong>
                    <p>{file.size} bytes</p>
                  </div>
                </button>
              ))}
            </div>
            <div className="skill-editor">
              <div className="mgr-actions">
                <span className="pill">{filePath}</span>
                <button className="mgr-btn" onClick={() => void handleSaveFile()}>保存文件</button>
              </div>
              <textarea value={fileContent} onChange={e => setFileContent(e.target.value)} rows={14} />
            </div>
          </div>
        </>
      )}

      {findings.length > 0 && (
        <>
          <div className="mgr-section-title">扫描详情</div>
          <div className="mgr-list">
            {findings.map((finding, idx) => (
              <div className="mgr-item" key={`${finding.file}-${finding.line}-${idx}`}>
                <div className="mgr-item-main">
                  <h4>{finding.category} · {finding.file}:{finding.line}</h4>
                  <p>{finding.snippet}</p>
                </div>
                <span className="pill off">risk</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
