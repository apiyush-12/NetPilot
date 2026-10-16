import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CircleCheck, X } from 'lucide-react'
import { API_BASE, apiGet, apiPost } from './lib/api.js'
import { Header, Sidebar } from './components/Chrome.jsx'
import ConfirmDialog, { TokenDialog } from './components/ConfirmDialog.jsx'
import Operations from './pages/Operations.jsx'
import Monitoring from './pages/Monitoring.jsx'
import Recovery from './pages/Recovery.jsx'
import Events from './pages/Events.jsx'
import Cloud from './pages/Cloud.jsx'
import CloudEvents from './pages/CloudEvents.jsx'
import Audit from './pages/Audit.jsx'
import Settings from './pages/Settings.jsx'
import { formatClock, loadSettings, normalizeSettings, saveSettings } from './lib/settings.js'

const ACTIONS = {
  lab: { start: ['Start the complete Docker lab', 'Start all existing NetPilot containers. This does not recreate missing containers.', false], stop: ['Stop the entire Docker lab', 'All NetPilot containers will stop and connectivity will be lost. Stop the controller first.', true] },
  routes: { 'reset-primary': ['Reset routes to Router A', 'Rewrite both client and server routes to use Router A. The controller must be stopped.', true] },
  service: { start: ['Start network node', 'Start this Docker service.', false], restart: ['Restart network node', 'Restarting an active service can interrupt connectivity and trigger recovery.', true], stop: ['Stop network node', 'This may break connectivity and trigger failover if automation is running.', true] },
  process: { start: ['Start supervised process', 'The backend will start and supervise this Python process.', false], stop: ['Stop supervised process', 'The backend will stop only the process it started.', true] }
}

const PAGE = {
  operations: Operations, monitoring: Monitoring, recovery: Recovery,
  events: Events, cloud: Cloud, 'cloud-events': CloudEvents, audit: Audit, settings: Settings
}

export default function App() {
  const [settings, setSettings] = useState(loadSettings)
  const [view, setView] = useState(() => loadSettings().landingPage)
  const [now, setNow] = useState(new Date())
  const [backendOnline, setBackendOnline] = useState(false)
  const [status, setStatus] = useState(null)
  const [events, setEvents] = useState([])
  const [incidents, setIncidents] = useState([])
  const [audit, setAudit] = useState([])
  const [logs, setLogs] = useState({ controller: [], forwarder: [] })
  const [cloud, setCloud] = useState(null)
  const [cloudLoading, setCloudLoading] = useState(false)
  const [token, setToken] = useState('')
  const [tempToken, setTempToken] = useState('')
  const [tokenDialog, setTokenDialog] = useState(false)
  const [confirmRequest, setConfirmRequest] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [streamOnline, setStreamOnline] = useState(false)
  const eventsRef = useRef([])
  const alertIds = useRef(new Set())

  const updateSetting = (key, value) => setSettings(current => normalizeSettings({ ...current, [key]: value }))
  const lockControls = () => { setToken(''); setTempToken(''); setNotice({ type: 'success', text: 'Control token cleared from console memory.' }) }
  useEffect(() => {
    saveSettings(settings)
    const root = document.documentElement
    root.classList.toggle('np-midnight', settings.theme === 'midnight')
    root.classList.toggle('np-blue', settings.accent === 'blue')
    root.classList.toggle('np-amber', settings.accent === 'amber')
    root.classList.toggle('np-compact', settings.density === 'compact')
    root.classList.toggle('np-large-text', settings.textScale === 'large')
  }, [settings])

  const refreshStatus = useCallback(async () => {
    try { const data = await apiGet('/api/status'); setStatus(data); setBackendOnline(true) }
    catch { setBackendOnline(false); setStatus(null) }
  }, [])

  const refreshEvents = useCallback(async () => {
    try {
      const data = await apiGet('/api/events?limit=300')
      const list = [...(data.items || [])].reverse()
      eventsRef.current = list
      setEvents(list)
    } catch { /* Service health shown separately */ }
  }, [])
  const refreshIncidents = useCallback(async () => { try { const data = await apiGet('/api/incidents?limit=100'); setIncidents(data.items || []) } catch { /* retain last known */ } }, [])
  const refreshAudit = useCallback(async () => { try { const data = await apiGet('/api/audit?limit=100'); setAudit([...(data.items || [])].reverse()) } catch { /* retain last known */ } }, [])
  const refreshLogs = useCallback(async () => {
    const [a,b] = await Promise.allSettled([apiGet('/api/logs/controller?limit=120'), apiGet('/api/logs/forwarder?limit=120')])
    setLogs(old => ({ controller: a.status === 'fulfilled' ? a.value.lines : old.controller, forwarder: b.status === 'fulfilled' ? b.value.lines : old.forwarder }))
  }, [])
  const refreshCloud = useCallback(async () => {
    setCloudLoading(true)
    try { const data = await apiGet('/api/cloud/status'); setCloud(data) }
    catch (error) { setNotice({ type: 'error', text: 'AWS status query failed: ' + error.message }) }
    finally { setCloudLoading(false) }
  }, [])

  const refreshAll = useCallback(() => {
    refreshStatus(); refreshEvents(); refreshIncidents(); refreshAudit(); refreshLogs();
    if (view === 'cloud') refreshCloud()
  }, [refreshStatus,refreshEvents,refreshIncidents,refreshAudit,refreshLogs,refreshCloud,view])

  useEffect(() => { refreshStatus(); refreshEvents(); refreshIncidents(); refreshAudit(); refreshLogs() }, []) // initial local fetch only; cloud page fetches on entry
  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])
  useEffect(() => {
    if (!settings.statusRefresh) return
    const interval = setInterval(refreshStatus, settings.statusRefresh * 1000)
    return () => clearInterval(interval)
  }, [refreshStatus, settings.statusRefresh])
  useEffect(() => {
    if (!settings.activityRefresh) return
    const interval = setInterval(() => { refreshIncidents(); refreshLogs() }, settings.activityRefresh * 1000)
    return () => clearInterval(interval)
  }, [refreshIncidents, refreshLogs, settings.activityRefresh])
  useEffect(() => {
    if (view !== 'cloud' || !settings.cloudStatusRefresh) return
    const interval = setInterval(refreshCloud, settings.cloudStatusRefresh * 1000)
    return () => clearInterval(interval)
  }, [view, settings.cloudStatusRefresh, refreshCloud])
  useEffect(() => { if (view === 'cloud') refreshCloud() }, [view, refreshCloud])
  useEffect(() => {
    if (!settings.streamEnabled) { setStreamOnline(false); return }
    const source = new EventSource(`${API_BASE}/api/events/stream`)
    source.onopen = () => { setStreamOnline(true); refreshEvents() }
    source.onerror = () => setStreamOnline(false)
    const receive = event => {
      try {
        const item = JSON.parse(event.data)
        setEvents(current => {
          if (current.some(old => old.event_id === item.event_id)) return current
          return [item, ...current].slice(0, 300)
        })
        if (['INCIDENT_CREATED','INCIDENT_RESOLVED','FAULT_DIAGNOSED','INCIDENT_DEGRADED'].includes(item.event)) refreshIncidents()
        if (item.event_id && !alertIds.current.has(item.event_id)) {
          alertIds.current.add(item.event_id)
          if (alertIds.current.size > 500) alertIds.current.clear()
          if (item.event === 'INCIDENT_CREATED' && settings.incidentAlerts)
            setNotice({ type: 'error', text: `Network incident created: ${item.incident_id || item.event_id}` })
          if (item.event === 'INCIDENT_RESOLVED' && settings.recoveryAlerts)
            setNotice({ type: 'success', text: `Incident resolved: ${item.incident_id || item.event_id}` })
        }
      } catch { /* ignore malformed SSE line */ }
    }
    source.addEventListener('log', receive)
    return () => { source.removeEventListener('log', receive); source.close() }
  }, [refreshEvents, refreshIncidents, settings.streamEnabled, settings.incidentAlerts, settings.recoveryAlerts])

  const requestAction = (kind, action, target) => {
    const [title, description, destructive] = ACTIONS[kind]?.[action] || ['Confirm action', '', true]
    const path = kind === 'lab' ? `/api/lab/${action}` : kind === 'routes' ? '/api/routes/reset-primary' : kind === 'service' ? `/api/services/${target}/${action}` : `/api/processes/${target}/${action}`
    setConfirmRequest({ title: target ? `${title}: ${target}` : title, description, destructive, path })
  }
  const executeAction = async () => {
    if (!confirmRequest) return
    setBusy(true)
    try {
      const result = await apiPost(confirmRequest.path, token)
      setNotice({ type: 'success', text: `Action completed: ${result?.action || confirmRequest.path} ${result?.target || ''}` })
      setConfirmRequest(null)
      setTimeout(refreshAll, 700)
    } catch(error) { setNotice({ type: 'error', text: `Action refused or failed: ${error.message}` }); setConfirmRequest(null) }
    finally { setBusy(false) }
  }
  const openIncident = id => { setSelectedIncident(id); setView('recovery') }
  const PageComponent = PAGE[view] || Operations

  let pageProps = {}
  if (view === 'operations') pageProps = { status, events, tokenLoaded: Boolean(token), busy, requestAction, setView, onIncident: openIncident }
  if (view === 'monitoring') pageProps = { status }
  if (view === 'recovery') pageProps = { incidents, events, selectedIncident, setSelectedIncident }
  if (view === 'events') pageProps = { events, logs, onIncident: openIncident, selectedIncident }
  if (view === 'cloud') pageProps = { cloud, cloudLoading, refreshCloud, setView }
  if (view === 'audit') pageProps = { items: audit }
  if (view === 'cloud-events') pageProps = { settings }
  if (view === 'settings') pageProps = { settings, onChange: updateSetting, onReplace: setSettings, onLock: lockControls, onUnlock: () => { setTempToken(token); setTokenDialog(true) }, tokenLoaded: Boolean(token), backendOnline }

  return <div className="app-shell">
    <Sidebar view={view} setView={setView} online={backendOnline} tokenLoaded={Boolean(token)}/>
    <div className="workspace"><Header view={view} online={backendOnline} status={status} now={now} clockText={formatClock(now, settings)} onRefresh={refreshAll} onUnlock={() => { setTempToken(token); setTokenDialog(true) }} tokenLoaded={Boolean(token)} busy={busy}/>
      {notice && <div className={`toast toast-${notice.type}`} role="status">{notice.type === 'success' ? <CircleCheck size={17}/> : <AlertTriangle size={17}/>}<span>{notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notice"><X size={15}/></button></div>}
      {!backendOnline && <div className="offline-banner"><AlertTriangle size={16}/> Backend is unreachable at {API_BASE}. Start FastAPI on 127.0.0.1:8000. Control actions remain disabled.</div>}
      <main className="main-content"><PageComponent {...pageProps}/></main>
      <footer className="app-footer"><span>CONTROL PLANE <span className={backendOnline ? 'good' : 'danger'}>{backendOnline ? 'CONNECTED' : 'OFFLINE'}</span></span><span>EVENT STREAM <span className={settings.streamEnabled && streamOnline ? 'good' : 'muted'}>{settings.streamEnabled ? (streamOnline ? 'LIVE' : 'RECONNECTING') : 'PAUSED'}</span></span><span className="footer-right">LOCAL DEVELOPMENT / DO NOT EXPOSE PORT 8000</span></footer>
    </div>
    <ConfirmDialog request={confirmRequest} onCancel={() => !busy && setConfirmRequest(null)} onConfirm={executeAction} busy={busy}/>
    <TokenDialog open={tokenDialog} onClose={() => setTokenDialog(false)} value={tempToken} setValue={setTempToken} onSave={() => { setToken(tempToken.trim()); setTokenDialog(false); setNotice({ type: 'success', text: 'Control token loaded in memory. Authorization will be checked by the backend on the next action.' }) }}/>
  </div>
}
