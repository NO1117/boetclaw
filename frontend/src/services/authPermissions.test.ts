import { describe, expect, it } from 'vitest'
import { hasPermission, type AuthUser } from './api'
import { clearAuthClientState, getCsrfToken, setCsrfToken } from './authClient'

describe('authClient CSRF', () => {
  it('stores short-lived CSRF in sessionStorage only', () => {
    clearAuthClientState()
    setCsrfToken('csrf-abc')
    expect(getCsrfToken()).toBe('csrf-abc')
    expect(sessionStorage.getItem('boetclaw_csrf')).toBe('csrf-abc')
    expect(localStorage.getItem('boetclaw_console_token')).toBeNull()
    clearAuthClientState()
    expect(getCsrfToken()).toBe('')
  })
})

describe('hasPermission gate', () => {
  it('allows open mode and explicit permission codes', () => {
    const openUser: AuthUser = { open_mode: true, role: 'owner' }
    expect(hasPermission(openUser, 'users:write')).toBe(true)
    const viewer: AuthUser = { role: 'viewer', permissions: ['audit:read_own'] }
    expect(hasPermission(viewer, 'tasks:create')).toBe(false)
    expect(hasPermission(viewer, 'audit:read_own')).toBe(true)
  })
})
