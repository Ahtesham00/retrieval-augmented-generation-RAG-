import { useAuthStore } from '../store/useAuthStore'

const BASE_URL = 'http://localhost:8000'

let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const refreshToken = useAuthStore.getState().refreshToken
  if (!refreshToken) return null
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return null
    const data = await res.json()
    useAuthStore.getState().setTokens(data.access_token, refreshToken)
    return data.access_token
  } catch {
    return null
  }
}

async function getNewToken(): Promise<string | null> {
  if (isRefreshing && refreshPromise) return refreshPromise
  isRefreshing = true
  refreshPromise = doRefresh().finally(() => {
    isRefreshing = false
    refreshPromise = null
  })
  return refreshPromise
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = useAuthStore.getState().token
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] ?? 'application/json'
  }

  let res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (res.status === 401) {
    const newToken = await getNewToken()
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`
      res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
    } else {
      useAuthStore.getState().logout()
      throw new Error('Session expired')
    }
  }

  return res
}

export async function apiJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, options)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export { BASE_URL }
