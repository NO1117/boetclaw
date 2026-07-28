import { useEffect, useState } from 'react'
import {
  fetchResourceAcl,
  fetchTeamUsers,
  grantResourceAccess,
  hasPermission,
  revokeResourceAccess,
  setResourceVisibility,
  type AuthUser,
  type ResourceAcl,
  type TeamUser,
} from '../services/api'

interface Props {
  resourceType: 'agent' | 'knowledge_base'
  resourceId: string
  currentUser: AuthUser | null | undefined
}

export default function ResourceAccessPanel({ resourceType, resourceId, currentUser }: Props) {
  const [acl, setAcl] = useState<ResourceAcl | null>(null)
  const [users, setUsers] = useState<TeamUser[]>([])
  const [grantUserId, setGrantUserId] = useState('')
  const [grantLevel, setGrantLevel] = useState('runner')
  const [error, setError] = useState('')
  const canEdit =
    hasPermission(currentUser, resourceType === 'agent' ? 'agents:admin' : 'kb:admin') ||
    currentUser?.role === 'owner' ||
    currentUser?.role === 'admin' ||
    currentUser?.open_mode

  const reload = async () => {
    const next = await fetchResourceAcl(resourceType, resourceId)
    setAcl(next)
  }

  useEffect(() => {
    reload().catch(err => setError(err instanceof Error ? err.message : '加载失败'))
    if (canEdit) {
      fetchTeamUsers()
        .then(setUsers)
        .catch(() => undefined)
    }
  }, [resourceType, resourceId])

  if (!acl) {
    return <div className="resource-access-panel">加载访问权限...</div>
  }

  return (
    <div className="resource-access-panel">
      <h3>访问权限</h3>
      {error && <div className="login-error">{error}</div>}
      <label>
        可见范围
        <select
          value={acl.visibility}
          disabled={!canEdit}
          onChange={async e => {
            try {
              const next = await setResourceVisibility(resourceType, resourceId, e.target.value)
              setAcl(next)
            } catch (err) {
              setError(err instanceof Error ? err.message : '更新失败')
            }
          }}
        >
          <option value="workspace">workspace</option>
          <option value="private">private</option>
        </select>
      </label>
      <ul>
        {acl.grants.map(g => (
          <li key={g.user_id}>
            {g.user_id.slice(0, 8)}… · {g.level}
            {canEdit && (
              <button
                type="button"
                onClick={async () => {
                  try {
                    const next = await revokeResourceAccess(resourceType, resourceId, g.user_id)
                    setAcl(next)
                  } catch (err) {
                    setError(err instanceof Error ? err.message : '撤销失败')
                  }
                }}
              >
                撤销
              </button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="grant-row">
          <select value={grantUserId} onChange={e => setGrantUserId(e.target.value)}>
            <option value="">选择用户</option>
            {users.map(u => (
              <option key={u.id} value={u.id}>
                {u.username} ({u.role})
              </option>
            ))}
          </select>
          <select value={grantLevel} onChange={e => setGrantLevel(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="runner">runner</option>
          </select>
          <button
            type="button"
            className="primary-btn"
            disabled={!grantUserId}
            onClick={async () => {
              try {
                const next = await grantResourceAccess(
                  resourceType,
                  resourceId,
                  grantUserId,
                  grantLevel,
                )
                setAcl(next)
              } catch (err) {
                setError(err instanceof Error ? err.message : '授权失败')
              }
            }}
          >
            授权
          </button>
        </div>
      )}
    </div>
  )
}
