import React, { useMemo, useState } from 'react'
import EventTable from '../components/EventTable.jsx'
import { Empty, Label, SectionHead } from '../components/Chrome.jsx'

export default function Events({ events, logs, onIncident, selectedIncident }) {
  const [filter, setFilter] = useState('')
  const [source, setSource] = useState('events')
  const [onlyImportant, setOnlyImportant] = useState(false)
  const visible = useMemo(() => events.filter(e => {
    const text = [e.event,e.incident_id,e.fault_type,e.reason,e.target].join(' ').toLowerCase()
    return text.includes(filter.toLowerCase()) && (!onlyImportant || !['NETWORK_HEALTHY','CONNECTIVITY_FAILURE'].includes(e.event))
  }), [events, filter, onlyImportant])
  const consoleLines = logs?.[source] || []
  return <div className="page"><div className="page-head"><div className="eyebrow">EVENT TELEMETRY / EVIDENCE</div><h2>Logs and audit explorer</h2><p>Filter NetPilot's local JSONL events, inspect controller output, or inspect the AWS forwarder log.</p></div>
    <section className="panel"><SectionHead title="STRUCTURED NETWORK EVENTS" detail="Last 300 local events, newest first" right={<div className="log-toolbar"><label className="checkbox-control"><input type="checkbox" checked={onlyImportant} onChange={e=>setOnlyImportant(e.target.checked)}/>HIDE HEARTBEATS</label><input className="text-input compact-input" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Search fault, ID, router..." aria-label="Filter events"/><Label>{visible.length} FOUND</Label></div>}/><EventTable items={visible} onIncident={onIncident} selectedIncident={selectedIncident}/></section>
    <section className="panel"><SectionHead title="PROCESS CONSOLE OUTPUT" detail="Read-only output from controller/forwarder processes started through this API" right={<select className="select-input" value={source} onChange={e=>setSource(e.target.value)} aria-label="Select process log"><option value="controller">NETPILOT CONTROLLER</option><option value="forwarder">AWS FORWARDER</option></select>}/><div className="terminal-log">{consoleLines.length ? consoleLines.slice(-90).map((line,i)=><div key={`${source}-${i}`}>{line}</div>) : <Empty text="No process output recorded under this backend instance."/>}</div></section>
  </div>
}
