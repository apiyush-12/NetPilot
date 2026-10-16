import React, { useMemo, useState } from 'react'
import { CheckCircle2, Clock, GitBranch, ShieldAlert, TriangleAlert } from 'lucide-react'
import { Empty, Label, SectionHead } from '../components/Chrome.jsx'
import { prettyDate, readableType, severityOf, shortId } from '../lib/format.js'

function stageFor(event) {
  switch (event) {
    case 'INCIDENT_CREATED': return 'DETECTION'
    case 'FAULT_DIAGNOSED': return 'DIAGNOSIS'
    case 'RECOVERY_ATTEMPT': case 'ROUTE_CHANGE_STARTED': return 'RECOVERY'
    case 'ROUTE_CHANGE_SUCCESS': case 'ROUTE_CHANGE_FAILED': return 'ROUTE CHANGE'
    case 'INCIDENT_RESOLVED': return 'RESOLUTION'
    case 'PRIMARY_STABLE': case 'FAILBACK_RESULT': return 'FAILBACK'
    default: return 'TELEMETRY'
  }
}

export default function Recovery({ incidents, events, selectedIncident, setSelectedIncident }) {
  const [search, setSearch] = useState('')
  const visible = useMemo(() => incidents.filter(item => [item.incident_id,item.fault_type,item.status].join(' ').toLowerCase().includes(search.toLowerCase())), [incidents,search])
  const selected = incidents.find(item => item.incident_id === selectedIncident) || visible[0] || null
  const incidentEvents = useMemo(() => events.filter(item => item.incident_id && item.incident_id === selected?.incident_id).slice().reverse(), [events, selected?.incident_id])
  return <div className="page"><div className="page-head"><div className="eyebrow">INCIDENT COMMAND / TIMELINE</div><h2>Recovery tracker</h2><p>Follow the controller's actual event sequence, from fault detection through route changes and verification. Events without incident IDs are displayed in Event Logs.</p></div>
    <div className="recovery-split">
      <section className="panel incident-index"><SectionHead title="INCIDENT REGISTER" detail={`${incidents.length} recently indexed incidents`} right={<input className="text-input compact-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter incidents" aria-label="Filter incidents"/>}/>
        <div className="incident-list">{visible.map(item => <button key={item.incident_id} className={`incident-row ${selected?.incident_id === item.incident_id ? 'active' : ''}`} onClick={() => setSelectedIncident(item.incident_id)}><div className="incident-row-top"><span className="cell-mono">#{shortId(item.incident_id, 12)}</span><Label tone={item.status === 'RESOLVED' ? 'good' : 'warn'}>{item.status}</Label></div><strong>{readableType(item.fault_type || 'UNCLASSIFIED INCIDENT')}</strong><span className="muted small-text">{prettyDate(item.created_at || item.last_event_at)}</span></button>)}{visible.length === 0 && <Empty text="No incidents match the filter."/>}</div>
      </section>
      <section className="panel incident-detail"><SectionHead title="RECOVERY EXECUTION TRACE" detail={selected ? `Incident ${selected.incident_id}` : 'Choose an incident to inspect'} right={selected && <Label tone={selected.status === 'RESOLVED' ? 'good' : 'warn'}>{selected.status}</Label>}/>
        {selected ? <>
          <div className="trace-meta"><div><span>FAULT CLASS</span><strong>{selected.fault_type || 'NOT CLASSIFIED'}</strong></div><div><span>CREATED</span><strong>{prettyDate(selected.created_at)}</strong></div><div><span>RESOLUTION</span><strong>{selected.resolution || 'NOT RESOLVED'}</strong></div></div>
          <div className="timeline">{incidentEvents.map((event, i) => <div key={event.event_id || i} className="timeline-entry"><div className={`timeline-dot ${severityOf(event.event)}`}>{severityOf(event.event) === 'good' ? <CheckCircle2 size={13}/> : severityOf(event.event) === 'danger' ? <TriangleAlert size={13}/> : <Clock size={13}/>}</div><div className="timeline-content"><div className="timeline-head"><span className="trace-stage">{stageFor(event.event)}</span><span className="muted small-text">{prettyDate(event.timestamp)}</span></div><strong>{readableType(event.event)}</strong><div className="trace-properties">{['fault_type','action','previous','target','reason','resolution','attempt','duration_ms','active_router','successful'].filter(k=> event[k] !== undefined && event[k] !== null).map(key=><span key={key}><em>{key}</em> {String(event[key])}</span>)}</div></div></div>)}{!incidentEvents.length && <Empty text="This incident is outside the last 300 loaded events. View Event Logs for a broader local history."/>}</div>
        </> : <Empty text="No incidents have been recorded."/>}
      </section>
    </div>
  </div>
}
