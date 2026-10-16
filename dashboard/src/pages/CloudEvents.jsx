import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, Database, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { apiGet } from '../lib/api.js'
import { Empty, Label, SectionHead } from '../components/Chrome.jsx'
import { prettyDate, readableType, severityOf, shortId } from '../lib/format.js'

const PAGE_SIZE = 50
const recoveryStages = {
  INCIDENT_CREATED: 'DETECTED',
  FAULT_DIAGNOSED: 'DIAGNOSED',
  RECOVERY_ATTEMPT: 'RECOVERING',
  ROUTE_CHANGE_STARTED: 'ROUTE CHANGE',
  ROUTE_CHANGE_SUCCESS: 'ROUTE VERIFIED',
  INCIDENT_RESOLVED: 'RESOLVED',
  FAILBACK_RESULT: 'FAILBACK'
}

function mergeItems(current, incoming) {
  const byId = new Map()
  for (const item of [...current, ...incoming]) {
    if (item.event_id) byId.set(item.event_id, item)
  }
  return Array.from(byId.values()).sort((a, b) => {
    const date = String(b.timestamp || '').localeCompare(String(a.timestamp || ''))
    return date || String(b.event_id).localeCompare(String(a.event_id))
  })
}

function groupIncidents(items) {
  const map = new Map()
  for (const item of items) {
    if (!item.incident_id) continue
    if (!map.has(item.incident_id)) map.set(item.incident_id, { id: item.incident_id, items: [] })
    map.get(item.incident_id).items.push(item)
  }
  return Array.from(map.values()).map(group => {
    group.items.sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)))
    group.fault = group.items.find(e => e.event_type === 'FAULT_DIAGNOSED')?.payload?.fault_type || 'UNCLASSIFIED'
    group.resolved = group.items.some(e => e.event_type === 'INCIDENT_RESOLVED')
    group.latest = group.items[group.items.length - 1]?.timestamp
    return group
  }).sort((a, b) => String(b.latest).localeCompare(String(a.latest)))
}

export default function CloudEvents({ settings }) {
  const refreshSeconds = settings?.cloudEventsRefresh ?? 30
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [filterType, setFilterType] = useState('ALL')
  const [tab, setTab] = useState('events')
  const [selectedId, setSelectedId] = useState(null)
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(refreshSeconds > 0)
  const busy = useRef(false)
  const mounted = useRef(true)

  const fetchPage = useCallback(async (nextCursor, mode) => {
    if (busy.current) return
    busy.current = true
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
      if (nextCursor) params.set('cursor', nextCursor)
      const result = await apiGet(`/api/cloud/events?${params}`)
      if (!mounted.current) return
      setItems(current => mode === 'replace' ? mergeItems([], result.items || []) : mergeItems(current, result.items || []))
      // Background refresh should not reset progress through older pages.
      if (mode !== 'merge') setCursor(result.next_cursor || null)
    } catch (err) {
      if (mounted.current) setError(err.message || 'Cloud event fetch failed')
    } finally {
      busy.current = false
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    fetchPage(null, 'replace')
    return () => { mounted.current = false }
  }, [fetchPage])
  useEffect(() => { setAutoRefresh(refreshSeconds > 0) }, [refreshSeconds])
  useEffect(() => {
    if (!autoRefresh || !refreshSeconds) return
    const timer = setInterval(() => fetchPage(null, 'merge'), refreshSeconds * 1000)
    return () => clearInterval(timer)
  }, [fetchPage, autoRefresh, refreshSeconds])

  const types = useMemo(() => [...new Set(items.map(e => e.event_type || 'UNKNOWN'))].sort(), [items])
  const visible = useMemo(() => items.filter(item => {
    if (filterType !== 'ALL' && item.event_type !== filterType) return false
    return [item.event_type, item.incident_id, item.event_id, item.source, item.payload?.fault_type,
      item.payload?.reason, item.payload?.target].join(' ').toLowerCase().includes(query.toLowerCase())
  }), [items, filterType, query])
  const groups = useMemo(() => groupIncidents(visible), [visible])
  const selected = items.find(item => item.event_id === selectedId)
  const selectedGroup = groups.find(group => group.id === selectedIncident)

  return <div className="page cloud-explorer">
    <div className="page-head"><div className="eyebrow">AWS / DYNAMODB / EVENT EVIDENCE</div>
      <h2>Cloud Event Explorer</h2>
      <p>Real records loaded from netpilot-events-dev. Search, inspect full payloads and trace cloud-stored incident history. No AWS credentials enter the browser.</p>
    </div>
    <section className="panel">
      <SectionHead title="EVENT STORE / LIVE READ" detail={`${items.length} unique records loaded · region ap-south-1 · ${cursor ? 'more pages available' : 'end of scan reached'}`}
        right={<div className="cloud-explorer-toolbar"><label className="checkbox-control"><input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)}/>AUTO-REFRESH / {refreshSeconds || "MANUAL"}{refreshSeconds ? "S" : ""}</label>
          <button className="button button-accent" onClick={() => fetchPage(null, 'replace')} disabled={loading}><RefreshCw size={13}/> {loading ? 'LOADING…' : 'REFRESH'}</button></div>}/>
      {error && <div className="diagnostic-error"><ShieldAlert size={14}/> {error}. Ensure FastAPI is running and the AWS CLI identity has DynamoDB Scan permission.</div>}
      <div className="cloud-explorer-filters">
        <div className="cloud-explorer-tabs"><button className={tab === 'events' ? 'selected' : ''} onClick={() => setTab('events')}>EVENTS</button><button className={tab === 'incidents' ? 'selected' : ''} onClick={() => setTab('incidents')}>INCIDENTS</button></div>
        <div className="cloud-search"><Search size={15}/><input className="text-input" placeholder="Search event, incident, fault, target..." aria-label="Search cloud events" value={query} onChange={e => setQuery(e.target.value)}/></div>
        <select className="select-input" aria-label="Filter cloud event type" value={filterType} onChange={e => setFilterType(e.target.value)}><option value="ALL">ALL EVENT TYPES</option>{types.map(type => <option key={type} value={type}>{type}</option>)}</select>
        <Label>{tab === 'events' ? visible.length : groups.length} SHOWN</Label>
      </div>
      <div className="cloud-explorer-split">
        <div className="cloud-explorer-table-wrap">
          {tab === 'events' ? <table className="data-table cloud-event-table"><thead><tr><th>EVENT TIME</th><th>EVENT TYPE</th><th>INCIDENT</th><th>SOURCE</th><th>DETAIL</th></tr></thead>
            <tbody>{visible.map(item => <tr key={item.event_id} className={selectedId === item.event_id ? 'row-selected' : ''}>
              <td className="cell-time">{prettyDate(item.timestamp)}</td><td><Label tone={severityOf(item.event_type)}>{readableType(item.event_type)}</Label></td>
              <td className="cell-mono" title={item.incident_id || 'No incident ID'}>{shortId(item.incident_id, 12)}</td>
              <td className="cell-mono">{item.source || '—'}</td>
              <td><button className="cloud-event-open" onClick={() => { setSelectedId(item.event_id); setSelectedIncident(item.incident_id) }} aria-label={`Inspect event ${item.event_id}`}><ChevronRight size={16}/></button></td>
            </tr>)}</tbody></table>
            : <div className="cloud-incident-list">{groups.map(group => <button key={group.id} className={`incident-row ${selectedIncident === group.id ? 'active' : ''}`} onClick={() => { setSelectedIncident(group.id); setSelectedId(null) }}>
              <div className="incident-row-top"><span className="cell-mono">#{shortId(group.id, 18)}</span><Label tone={group.resolved ? 'good' : 'warn'}>{group.resolved ? 'RESOLVED IN LOADED EVENTS' : 'NOT RESOLVED IN LOADED EVENTS'}</Label></div>
              <strong>{readableType(group.fault)}</strong><span className="muted small-text">{group.items.length} stored events in loaded pages · {prettyDate(group.latest)}</span>
            </button>)}</div>}
          {(tab === 'events' ? visible.length === 0 : groups.length === 0) && <Empty text={loading ? 'Loading DynamoDB records…' : 'No cloud records match this filter.'}/>}
          <div className="cloud-explorer-pagination"><span>Scan pages have no guaranteed global time order; rows are sorted within loaded records.</span>
            {cursor && <button className="button button-quiet" disabled={loading} onClick={() => fetchPage(cursor, 'append')}>{loading ? 'LOADING…' : 'LOAD MORE RECORDS'}</button>}</div>
        </div>
        <aside className="cloud-explorer-inspector">
          <div className="cloud-inspector-head"><Database size={15}/><strong>{selectedGroup && tab === 'incidents' ? 'INCIDENT EXECUTION TRACE' : 'EVENT INSPECTOR'}</strong></div>
          {tab === 'incidents' && selectedGroup ? <div className="cloud-trace">
            <div className="cloud-inspector-meta"><span>INCIDENT</span><code>{selectedGroup.id}</code></div>
            {selectedGroup.items.map(item => <button key={item.event_id} className="cloud-trace-step" onClick={() => { setTab('events'); setSelectedId(item.event_id) }}>
              <span className="muted small-text">{prettyDate(item.timestamp)}</span><strong>{recoveryStages[item.event_type] || 'EVENT'}</strong><span>{readableType(item.event_type)}</span>
              {item.payload?.fault_type && <small>{item.payload.fault_type}</small>}
            </button>)}
          </div> : selected ? <div className="cloud-inspector-body">
            <div className="cloud-inspector-meta"><span>EVENT ID</span><code>{selected.event_id}</code></div>
            <div className="cloud-inspector-meta"><span>INCIDENT ID</span><code>{selected.incident_id || '—'}</code></div>
            <div className="cloud-inspector-meta"><span>TYPE</span><strong>{readableType(selected.event_type)}</strong></div>
            <div className="cloud-inspector-meta"><span>RECEIVED</span><strong>{prettyDate(selected.received_at)}</strong></div>
            <div className="cloud-inspector-meta"><span>FULL STORED RECORD</span></div>
            <pre className="cloud-raw-json">{JSON.stringify(selected, null, 2)}</pre>
          </div> : <Empty text="Select a cloud event or incident to inspect its details."/>}
        </aside>
      </div>
    </section>
    <div className="foot-note">Read-only cloud data. The incident view groups currently loaded pages; load additional pages for older events. Full chronological queries will need a dedicated DynamoDB index.</div>
  </div>
}
