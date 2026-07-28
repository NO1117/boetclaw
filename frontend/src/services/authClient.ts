/** Browser-side CSRF / auth client state (no long-lived tokens in localStorage). */

const CSRF_STORAGE_KEY = 'boetclaw_csrf'

let memoryCsrf = ''

export function getCsrfToken(): string {
  return memoryCsrf || sessionStorage.getItem(CSRF_STORAGE_KEY) || ''
}

export function setCsrfToken(token: string) {
  memoryCsrf = token || ''
  if (token) sessionStorage.setItem(CSRF_STORAGE_KEY, token)
  else sessionStorage.removeItem(CSRF_STORAGE_KEY)
}

export function clearAuthClientState() {
  setCsrfToken('')
  localStorage.removeItem('boetclaw_console_token')
}

export function authHeaders(method = 'GET'): Record<string, string> {
  const headers: Record<string, string> = {}
  const csrf = getCsrfToken()
  const upper = method.toUpperCase()
  if (csrf && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(upper)) {
    headers['X-CSRF-Token'] = csrf
  }
  return headers
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers || {})
  for (const [k, v] of Object.entries(authHeaders(method))) {
    if (!headers.has(k)) headers.set(k, v)
  }
  return fetch(input, { ...init, headers, credentials: 'include' })
}
