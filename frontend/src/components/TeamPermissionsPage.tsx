import { useEffect, useState } from 'react'
import { Shield, UserPlus } from 'lucide-react'
import {
  createTeamUser,
  fetchTeamUsers,
  hasPermission,
  resetTeamUserPassword,
  revokeTeamUserSessions,
  updateTeamUser,
  type AuthUser,
  type TeamUser,
} from '../services/api'

interface Props {
  currentUser: AuthUser | null | undefined
}

export default function TeamPermissionsPage({ currentUser }: Props) {
  const [users, setUsers] = useState<TeamUser[]>([])
  const [error, setError] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState('operator')
  const canWrite = hasPermission(currentUser, 'users:write')

  const reload = async () => {
    const rows = await fetchTeamUsers()
    setUsers(rows)
  }

  useEffect(() => {
    reload().catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [])

  if (!hasPermission(currentUser, 'users:read')) {
    return (
      <div className="settings-panel">
        <h2>团队与权限</h2>
        <p>当前角色无权查看团队用户。</p>
      </div>
    )
  }

  return (
    <div className="settings-panel team-permissions">
      <div className="panel-header-row">
        <Shield size={18} />
        <h2>团队与权限</h2>
      </div>
      <p className="muted">单工作区本地账号。系统角色固定为 owner / admin / operator / viewer。</p>
      {error && <div className="login-error">{error}</div>}

      {canWrite && (
        <form
          className="team-create-form"
          onSubmit={async e => {
            e.preventDefault()
            setError('')
            try {
              await createTeamUser({
                username,
                password,
                display_name: displayName || username,
                role,
              })
              setUsername('')
              setPassword('')
              setDisplayName('')
              await reload()
            } catch (err) {
              setError(err instanceof Error ? err.message : '创建失败')
            }
          }}
        >
          <h3>
            <UserPlus size={16} /> 创建用户
          </h3>
          <input
            placeholder="用户名"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
          <input
            placeholder="显示名称"
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
          />
          <input
            type="password"
            placeholder="初始密码（至少 8 位）"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={8}
          />
          <select value={role} onChange={e => setRole(e.target.value)}>
            <option value="admin">admin</option>
            <option value="operator">operator</option>
            <option value="viewer">viewer</option>
            {currentUser?.role === 'owner' && <option value="owner">owner</option>}
          </select>
          <button type="submit" className="primary-btn">
            创建
          </button>
        </form>
      )}

      <table className="team-user-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>角色</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map(user => (
            <tr key={user.id}>
              <td>
                <div>{user.display_name || user.username}</div>
                <div className="muted">{user.username}</div>
              </td>
              <td>{user.role}</td>
              <td>{user.status}</td>
              <td className="team-actions">
                {canWrite && (
                  <>
                    <select
                      aria-label={`角色-${user.username}`}
                      value={user.role}
                      disabled={user.role === 'owner' && currentUser?.role !== 'owner'}
                      onChange={async e => {
                        try {
                          await updateTeamUser(user.id, { role: e.target.value })
                          await reload()
                        } catch (err) {
                          setError(err instanceof Error ? err.message : '更新失败')
                        }
                      }}
                    >
                      <option value="admin">admin</option>
                      <option value="operator">operator</option>
                      <option value="viewer">viewer</option>
                      <option value="owner">owner</option>
                    </select>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await updateTeamUser(user.id, {
                            status: user.status === 'active' ? 'disabled' : 'active',
                          })
                          await reload()
                        } catch (err) {
                          setError(err instanceof Error ? err.message : '状态更新失败')
                        }
                      }}
                    >
                      {user.status === 'active' ? '禁用' : '启用'}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        const next = window.prompt('新密码（至少 8 位）')
                        if (!next) return
                        try {
                          await resetTeamUserPassword(user.id, next)
                        } catch (err) {
                          setError(err instanceof Error ? err.message : '重置失败')
                        }
                      }}
                    >
                      重置密码
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await revokeTeamUserSessions(user.id)
                        } catch (err) {
                          setError(err instanceof Error ? err.message : '注销失败')
                        }
                      }}
                    >
                      注销会话
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
