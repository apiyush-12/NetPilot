import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_SETTINGS, STORAGE_KEY, normalizeSettings, loadSettings, saveSettings, formatClock, dateOptions, applyConsoleTheme, EXTRA_CONSOLE_THEMES } from '../src/lib/settings.js'

test('defaults are valid', () => {
  assert.deepEqual(normalizeSettings({}), DEFAULT_SETTINGS)
})

test('allows supported values including manual polling', () => {
  const result = normalizeSettings({ statusRefresh: 0, cloudEventsRefresh: 120, accent: 'amber', theme: 'midnight', streamEnabled: false })
  assert.equal(result.statusRefresh, 0)
  assert.equal(result.cloudEventsRefresh, 120)
  assert.equal(result.accent, 'amber')
  assert.equal(result.streamEnabled, false)
})

test('rejects unknown preferences and unsupported values', () => {
  const result = normalizeSettings({ controlToken: 'sensitive', awsSecret: 'sensitive', statusRefresh: 999, landingPage: 'hacker' })
  assert.equal(result.statusRefresh, 5)
  assert.equal(result.landingPage, 'operations')
  assert.equal('controlToken' in result, false)
  assert.equal('awsSecret' in result, false)
})

test('normalizes malformed settings', () => {
  assert.deepEqual(normalizeSettings(null), DEFAULT_SETTINGS)
  assert.deepEqual(normalizeSettings([]), DEFAULT_SETTINGS)
  assert.deepEqual(normalizeSettings('bad'), DEFAULT_SETTINGS)
})

test('writes UI preferences only to the local storage key', () => {
  const storage = new Map()
  globalThis.window = { localStorage: { setItem: (k,v) => storage.set(k,v), getItem: k => storage.get(k) || null } }
  const result = saveSettings({ ...DEFAULT_SETTINGS, theme: 'midnight', secretKey: 'not saved' })
  assert.equal(result.theme, 'midnight')
  assert.equal('secretKey' in result, false)
  assert.ok(storage.has(STORAGE_KEY))
  assert.equal(JSON.parse(storage.get(STORAGE_KEY)).theme, 'midnight')
  assert.equal('secretKey' in JSON.parse(storage.get(STORAGE_KEY)), false)
  assert.equal(loadSettings().theme, 'midnight')
})

test('clock displays timezone indicator for UTC', () => {
  const date = new Date('2026-10-14T18:00:00Z')
  assert.match(formatClock(date, { clockZone: 'utc', clockFormat: '24h' }), /UTC$/)
  assert.equal(dateOptions({ clockZone:'utc',clockFormat:'12h' }).timeZone, 'UTC')
})


test('all six console themes are allow-listed', () => {
  for (const theme of ['dark', 'midnight', 'carbon', 'navy', 'terminal', 'industrial']) {
    assert.equal(normalizeSettings({ theme }).theme, theme)
  }
  assert.equal(normalizeSettings({ theme: 'unknown' }).theme, DEFAULT_SETTINGS.theme)
})

test('extra themes select one root class and remove the previous one', () => {
  const classes = new Set()
  globalThis.document = { documentElement: { classList: { toggle: (name, yes) => {
    if (yes) classes.add(name)
    else classes.delete(name)
  } } } }
  applyConsoleTheme('terminal')
  assert.deepEqual([...classes], ['np-terminal'])
  applyConsoleTheme('industrial')
  assert.deepEqual([...classes], ['np-industrial'])
  applyConsoleTheme('dark')
  assert.deepEqual([...classes], [])
  assert.equal(EXTRA_CONSOLE_THEMES.length, 4)
  delete globalThis.document
})
