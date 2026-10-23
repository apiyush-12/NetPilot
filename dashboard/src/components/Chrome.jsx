import React from 'react'
import { Activity, Cloud, Database, Command, FileText, GitBranch, History, LockKeyhole, Radio, Shield, ShieldCheck, SlidersHorizontal, TerminalSquare, BrainCircuit } from 'lucide-react'

export const NAV = [
  { id: 'operations', label: 'Control Center', icon: Command },
  { id: 'monitoring', label: 'Monitoring', icon: Activity },
  { id: 'recovery', label: 'Recovery Tracker', icon: GitBranch },
  { id: 'ai-operations', label: 'AI Operations', icon: BrainCircuit },
  { id: 'events', label: 'Event Logs', icon: TerminalSquare },
  { id: 'cloud', label: 'AWS Operations', icon: Cloud },
  { id: 'cloud-events', label: 'Cloud Events', icon: Database },
  { id: 'audit', label: 'Action Audit', icon: History },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal }
]

export function Sidebar({ view, setView, online, tokenLoaded }) {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-symbol">N<span>·</span></div><div><strong>NETPILOT</strong><small>OPERATIONS SYSTEM</small></div></div>
    <div className="nav-caption">WORKSPACE </div>
    <nav className="side-nav" aria-label="Primary navigation">
      {NAV.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${view === id ? 'selected' : ''}`} onClick={() => setView(id)}>
        <Icon size={16} strokeWidth={1.8} /><span>{label}</span>{view === id && <i />}
      </button>)}
    </nav>
    <div className="sidebar-foot">
      <div className="sidebar-foot-line"><Radio size={13}/><span>LOCAL CONTROL PLANE</span></div>
      <div className="sidebar-foot-line"><span className={`led ${online ? 'led-good' : 'led-bad'}`}/><span>{online ? 'API RESPONDING' : 'API UNAVAILABLE'}</span></div>
      <div className="sidebar-foot-line">{tokenLoaded ? <ShieldCheck size={13}/> : <LockKeyhole size={13}/>}<span>{tokenLoaded ? 'TOKEN LOADED' : 'CONTROLS LOCKED'}</span></div>
      <div className="version">NETPILOT / CONSOLE v0.1</div>
    </div>
  </aside>
}

export function Header({ view, online, status, now, clockText, onRefresh, onUnlock, tokenLoaded, busy }) {
  const current = NAV.find(v => v.id === view)
  return <header className="topbar">
    <div className="topbar-identity"><div className="breadcrumb">NETPILOT <span>/</span> WORKSPACE</div><h1>{current?.label || 'Operations'}</h1></div>
    <div className="topbar-right">
      <div className="header-status"><span className={`led ${online ? 'led-good' : 'led-bad'}`} />{online ? 'BACKEND ONLINE' : 'BACKEND OFFLINE'}</div>
      <div className="header-time">{clockText || now.toLocaleTimeString()}</div>
      <button className="button button-quiet" onClick={onRefresh} disabled={busy}>REFRESH</button>
      <button className="button button-accent" onClick={onUnlock}>{tokenLoaded ? 'TOKEN LOADED' : 'UNLOCK CONTROLS'}</button>
    </div>
  </header>
}

export function Label({ tone = 'neutral', children }) {
  return <span className={`tag tag-${tone}`}>{children}</span>
}

export function SectionHead({ title, detail, right }) {
  return <div className="section-head"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{right && <div className="section-actions">{right}</div>}</div>
}

export function Empty({ text = 'No records available.' }) { return <div className="empty"><FileText size={22}/><span>{text}</span></div> }
