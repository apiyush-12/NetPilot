import { dateOptions, loadSettings } from './settings.js'
export function prettyDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, dateOptions(loadSettings())) + (loadSettings().clockZone === 'utc' ? ' UTC' : '')
}

export function shortTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString(undefined, dateOptions(loadSettings())) + (loadSettings().clockZone === 'utc' ? ' UTC' : '')
}

export function shortId(value, count = 8) {
  return typeof value === 'string' && value.length > count ? value.slice(0, count) + '…' : (value || '—')
}

export function readableType(value) {
  return String(value || 'UNKNOWN').replace(/_/g, ' ')
}

export function severityOf(value) {
  const code = String(value || '').toUpperCase()
  if (/FAILED|FAILURE|UNAVAILABLE|DOWN|ERROR|DEGRADED|REQUIRED/.test(code)) return 'danger'
  if (/STARTED|CREATED|RETRY|MISMATCH|ATTEMPT|DIAGNOSED|STOPPED/.test(code)) return 'warn'
  if (/SUCCESS|RESOLVED|HEALTHY|STABLE|RECOVERED/.test(code)) return 'good'
  return 'neutral'
}

export function isPositive(value) { return value === true }
