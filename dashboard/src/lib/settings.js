// Only non-secret UI preferences are kept in this browser's localStorage.
// Do not add API keys, control tokens, AWS credentials, or incident payloads here.
export const STORAGE_KEY = 'netpilot.console.preferences.v1'

export const DEFAULT_SETTINGS = Object.freeze({
  theme: 'dark',
  accent: 'teal',
  density: 'comfortable',
  textScale: 'normal',
  statusRefresh: 5,
  activityRefresh: 8,
  cloudStatusRefresh: 0,
  cloudEventsRefresh: 30,
  streamEnabled: true,
  incidentAlerts: true,
  recoveryAlerts: true,
  clockZone: 'local',
  clockFormat: '24h',
  landingPage: 'operations'
})

const ALLOWED = {
  theme: ['dark', 'midnight', 'carbon', 'navy', 'terminal', 'industrial', 'copper', 'light'],
  accent: ['teal', 'blue', 'amber'],
  density: ['comfortable', 'compact'],
  textScale: ['normal', 'large'],
  statusRefresh: [0, 5, 10, 30],
  activityRefresh: [0, 8, 15, 30],
  cloudStatusRefresh: [0, 60, 120],
  cloudEventsRefresh: [0, 30, 60, 120],
  streamEnabled: [true, false],
  incidentAlerts: [true, false],
  recoveryAlerts: [true, false],
  clockZone: ['local', 'utc'],
  clockFormat: ['12h', '24h'],
  landingPage: ['operations', 'monitoring', 'recovery', 'events', 'cloud', 'cloud-events', 'audit', 'settings']
}

export function normalizeSettings(value) {
  const source = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  return Object.fromEntries(Object.entries(DEFAULT_SETTINGS).map(([key, fallback]) => [
    key, ALLOWED[key].includes(source[key]) ? source[key] : fallback
  ]))
}

// Additional visual themes are applied here so no App.jsx replacement is needed.
// App.jsx continues to manage Graphite/Midnight, accent, density and text size.
export const EXTRA_CONSOLE_THEMES = ['carbon', 'navy', 'terminal', 'industrial', 'copper', 'light']
export function applyConsoleTheme(theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  for (const id of EXTRA_CONSOLE_THEMES) {
    root.classList.toggle(`np-${id}`, theme === id)
  }
}

let cache = null
export function loadSettings() {
  if (cache) { applyConsoleTheme(cache.theme); return cache }
  try {
    cache = normalizeSettings(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}'))
  } catch {
    cache = normalizeSettings({})
  }
  applyConsoleTheme(cache.theme)
  return cache
}

export function saveSettings(value) {
  cache = normalizeSettings(value)
  applyConsoleTheme(cache.theme)
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cache)) } catch { /* Browser storage may be disabled */ }
  return cache
}

export function formatClock(date, settings) {
  const options = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: settings.clockFormat === '12h' }
  if (settings.clockZone === 'utc') options.timeZone = 'UTC'
  return date.toLocaleTimeString(undefined, options) + (settings.clockZone === 'utc' ? ' UTC' : '')
}

export function dateOptions(settings) {
  const options = { hour12: settings.clockFormat === '12h' }
  if (settings.clockZone === 'utc') options.timeZone = 'UTC'
  return options
}
