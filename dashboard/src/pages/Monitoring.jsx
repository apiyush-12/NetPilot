import React from 'react'
import Topology from '../components/Topology.jsx'
import { Label, SectionHead } from '../components/Chrome.jsx'
import { prettyDate } from '../lib/format.js'

export default function Monitoring({ status }) {
  const services = status?.services || {}
  const routes = status?.routes || {}
  return <div className="page">
    <div className="page-head"><div className="eyebrow">REAL-TIME MONITORING / LOCAL LAB</div><h2>Network health and routing</h2><p>Observed from Docker containers every few seconds. This screen does not fabricate latency or packet-loss graphs.</p></div>
    <section className="panel"><SectionHead title="TOPOLOGY" detail="Forwarding-path illustration based on inspected routes" right={<Label tone={status?.connected ? 'good' : 'danger'}>{status?.connected ? 'END-TO-END OK' : status?.connected === false ? 'CHECK FAILED' : 'CHECK UNKNOWN'}</Label>}/><Topology status={status}/></section>
    <div className="monitor-split">
      <section className="panel"><SectionHead title="L3 ROUTING TABLE" detail="Gateways determined by ip -4 route get"/><table className="details-table"><tbody><tr><th>Client gateway</th><td className="cell-mono">{routes.client_gateway || 'Not observable'}</td></tr><tr><th>Server return gateway</th><td className="cell-mono">{routes.server_gateway || 'Not observable'}</td></tr><tr><th>Controller interpretation</th><td><Label tone={status?.active_router === 'mismatch' ? 'warn' : 'neutral'}>{status?.active_router || 'UNKNOWN'}</Label></td></tr><tr><th>End-to-end probe</th><td>{status?.connected == null ? 'Unknown' : status.connected ? 'Success' : 'Failed'}</td></tr><tr><th>Last sampled</th><td>{prettyDate(status?.timestamp)}</td></tr></tbody></table>
      {Boolean(status?.route_errors?.length) && <div className="diagnostic-error">{status.route_errors.join(' / ')}</div>}</section>
      <section className="panel"><SectionHead title="DOCKER NODE INVENTORY" detail="Current container state"/><table className="data-table"><thead><tr><th>SERVICE</th><th>RUNNING</th><th>COMPOSE STATE</th></tr></thead><tbody>{['client','router-a','router-b','server'].map(id => <tr key={id}><td className="cell-mono">{id}</td><td><Label tone={services[id]?.running ? 'good' : 'danger'}>{services[id]?.running ? 'UP' : 'DOWN'}</Label></td><td className="muted">{services[id]?.status || 'Unavailable'}</td></tr>)}</tbody></table>
        <div className="foot-note">If a container is stopped, its routing table may be unobservable. “Unknown” is not necessarily a route mismatch.</div>
      </section>
    </div>
  </div>
}
