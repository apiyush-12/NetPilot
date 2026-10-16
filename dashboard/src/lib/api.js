export const API_BASE = import.meta.env.VITE_NETPILOT_API_BASE || 'http://127.0.0.1:8000'

export async function apiGet(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`GET ${path}: HTTP ${response.status}`)
  return response.json()
}

export async function apiPost(path, token) {
  if (!token) throw new Error('Unlock controls with your temporary local control token first.')
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'X-NetPilot-Token': token },
    cache: 'no-store'
  })
  let body = null
  try { body = await response.json() } catch { /* response may be empty */ }
  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`
    throw new Error(detail)
  }
  return body
}
