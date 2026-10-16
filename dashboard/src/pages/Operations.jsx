import React from 'react'
import { Activity, ArrowDownUp, CirclePlay, CircleStop, Power, RefreshCw, RotateCcw, ServerCog, Wrench } from 'lucide-react'
import Topology from '../components/Topology.jsx'
import EventTable from '../components/EventTable.jsx'
import { Label, SectionHead } from '../components/Chrome.jsx'

const SERVICES = ['client', 'router-a', 'router-b', 'server']

export default function Operations({ status, events, tokenLoaded, busy, requestAction, setView, onIncident }) {
  const services = status?.services || {}
  const processes = status?.processes || {}
  const controllerRunning = Boolean(processes.controller)
  return <div className="page page-operations">
    <div className="metric-strip">
      <div><span className="metric-label">NETWORK STATE</span><strong className={status?.connected === true ? 'good' : status?.connected === false ? 'danger' : ''}>{status?.connected === true ? 'REACHABLE' : status?.connected === false ? 'UNREACHABLE' : 'UNKNOWN'}</strong></div>
      <div><span className="metric-label">ACTIVE PATH</span><strong>{(status?.active_router || 'UNKNOWN').toUpperCase()}</strong></div>
      <div><span className="metric-label">AUTOMATION</span><strong className={controllerRunning ? 'good' : 'muted'}>{controllerRunning ? 'RUNNING' : 'STOPPED'}</strong></div>
      <div><span className="metric-label">AWS FORWARDER</span><strong className={processes.forwarder ? 'good' : 'muted'}>{processes.forwarder ? 'RUNNING' : 'STOPPED'}</strong></div>
    </div>
    <div className="ops-command-bar"><div><span className="eyebrow">LAB COMMANDS</span><span className="bar-note">Commands execute on local Docker. Confirmation required.</span></div><div className="button-row">
      <button className="button button-neutral" disabled={busy || !tokenLoaded} onClick={() => requestAction('lab','start')}><Power size={14}/> START LAB</button>
      <button className="button button-neutral" disabled={busy || !tokenLoaded || controllerRunning} onClick={() => requestAction('routes','reset-primary')}><RotateCcw size={14}/> RESET PRIMARY</button>
      <button className="button button-danger-outline" disabled={busy || !tokenLoaded || controllerRunning} onClick={() => requestAction('lab','stop')}><CircleStop size={14}/> STOP LAB</button>
    </div></div>
    <div className="ops-split">
      <section className="panel topology-panel"><SectionHead title="LIVE NETWORK TOPOLOGY" detail="Actual container states and L3 route selection" right={<span className="mini-label">READ FROM /api/status</span>}/><Topology status={status}/></section>
      <section className="panel ops-service-panel"><SectionHead title="NODE CONTROL" detail="Predefined Docker service actions"/>
        <div className="table-scroll"><table className="data-table service-table"><thead><tr><th>NODE</th><th>STATE</th><th>CONTROLS</th></tr></thead><tbody>
          {SERVICES.map(service => <tr key={service}><td><strong className="node-name">{service.toUpperCase()}</strong><span className="service-sub">{services[service]?.status || 'Status unavailable'}</span></td><td><Label tone={services[service]?.running ? 'good' : 'danger'}>{services[service]?.state || 'UNKNOWN'}</Label></td><td><div className="row-actions"><button className="mini-button" onClick={() => requestAction('service','start',service)} disabled={busy || !tokenLoaded || services[service]?.running} title={`Start ${service}`}><CirclePlay size={14}/></button><button className="mini-button" onClick={() => requestAction('service','restart',service)} disabled={busy || !tokenLoaded || !services[service]?.running} title={`Restart ${service}`}><RefreshCw size={14}/></button><button className="mini-button mini-danger" onClick={() => requestAction('service','stop',service)} disabled={busy || !tokenLoaded || !services[service]?.running} title={`Stop ${service}`}><CircleStop size={14}/></button></div></td></tr>)}
        </tbody></table></div>
        <div className="panel-inside-head">MANAGED SERVICES</div>
        <div className="process-controls">
          {[['controller','NETPILOT v4 AGENT'],['forwarder','AWS EVENT FORWARDER']].map(([id, label]) => <div className="process-row" key={id}><div><strong>{label}</strong><span className="muted small-text">{processes[id] ? 'RUNNING UNDER API' : 'NOT RUNNING UNDER API'}</span></div><div className="process-btn-group"><Label tone={processes[id] ? 'good' : 'neutral'}>{processes[id] ? 'RUNNING' : 'STOPPED'}</Label><button className="mini-button" disabled={busy || !tokenLoaded || processes[id]} onClick={() => requestAction('process','start',id)} title={`Start ${id}`}><CirclePlay size={14}/></button><button className="mini-button mini-danger" disabled={busy || !tokenLoaded || !processes[id]} onClick={() => requestAction('process','stop',id)} title={`Stop ${id}`}><CircleStop size={14}/></button></div></div>)}
        </div>
      </section>
    </div>
    <section className="panel"><SectionHead title="LATEST TELEMETRY" detail="Incoming event log; newest first" right={<button className="button button-quiet" onClick={() => setView('events')}>OPEN EVENT EXPLORER →</button>}/><EventTable items={events} maxRows={7} onIncident={onIncident}/></section>
    <div className="foot-note"><Wrench size={14}/> ROUTINE OPERATIONS: The console executes real allowlisted backend actions. The controller and forwarder must not also be running in external terminals.</div>
  </div>
}
