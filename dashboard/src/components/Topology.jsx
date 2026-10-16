import React from 'react'
import { Label } from './Chrome.jsx'

const NODES = [
  { id: 'client', x: 38, y: 153, w: 126, label: 'CLIENT / 01', ip: '10.66.1.10' },
  { id: 'router-a', x: 282, y: 55, w: 128, label: 'ROUTER A', ip: 'PRIMARY' },
  { id: 'router-b', x: 282, y: 248, w: 128, label: 'ROUTER B', ip: 'STANDBY' },
  { id: 'server', x: 536, y: 153, w: 126, label: 'SERVER / 01', ip: '10.66.2.10' }
]

export default function Topology({ status }) {
  const services = status?.services || {}
  const current = status?.active_router
  const connected = status?.connected === true
  const isKnown = status?.docker_online === true
  const pathA = current === 'router-a' && connected
  const pathB = current === 'router-b' && connected
  const pathClass = (route, active) => {
    if (!services[route]?.running) return 'topo-path topo-dead'
    return active ? 'topo-path topo-active' : 'topo-path topo-standby'
  }
  return <div className="topology">
    <div className="topology-labels"><span>SEGMENT / CLIENT_LAN · 10.66.1.0/24</span><span>SEGMENT / SERVER_LAN · 10.66.2.0/24</span></div>
    <svg viewBox="0 0 700 370" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Network topology: client connected to router A and router B, then server. Active routes highlighted.">
      <defs><pattern id="topo-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" stroke="#26343b" strokeWidth=".65" fill="none" opacity=".75" /></pattern></defs>
      <rect width="700" height="370" fill="url(#topo-grid)"/>
      <text x="22" y="25" className="topo-small">NETPILOT / LAB TOPOLOGY</text>
      <text x="679" y="25" textAnchor="end" className="topo-small">L3 / DOCKER BRIDGES</text>
      <path d="M164 182 L217 182 L217 85 L282 85" className={pathClass('router-a', pathA)}/>
      <path d="M410 85 L480 85 L480 182 L536 182" className={pathClass('router-a', pathA)}/>
      <path d="M164 182 L217 182 L217 278 L282 278" className={pathClass('router-b', pathB)}/>
      <path d="M410 278 L480 278 L480 182 L536 182" className={pathClass('router-b', pathB)}/>
      {NODES.map(node => {
        const running = services[node.id]?.running
        const className = !isKnown ? 'unknown' : running ? 'up' : 'down'
        return <g key={node.id}>
          <rect x={node.x} y={node.y} width={node.w} height="58" className={`topo-node ${className}`}/>
          <rect x={node.x} y={node.y} width="4" height="58" className={`topo-node-strip ${className}`}/>
          <text x={node.x + 14} y={node.y + 22} className="topo-node-main">{node.label}</text>
          <text x={node.x + 14} y={node.y + 41} className="topo-node-sub">{node.ip}</text>
          <circle cx={node.x + node.w - 14} cy={node.y + 14} r="4" className={`topo-light ${className}`}/>
        </g>
      })}
      <text x="346" y="37" textAnchor="middle" className="topo-small">PRIMARY ROUTE</text>
      <text x="346" y="344" textAnchor="middle" className="topo-small">BACKUP ROUTE</text>
    </svg>
    <div className="topology-foot"><div><span className="route-key active"/> ACTIVE PATH</div><div><span className="route-key standby"/> AVAILABLE / STANDBY</div><div><span className="route-key down"/> UNAVAILABLE</div><div className="topology-current">CURRENT: <Label tone={current === 'mismatch' ? 'warn' : connected ? 'good' : 'neutral'}>{(current || 'UNKNOWN').toUpperCase()}</Label></div></div>
  </div>
}
