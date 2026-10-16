import React from 'react'
import { Empty, Label, SectionHead } from '../components/Chrome.jsx'
import { prettyDate } from '../lib/format.js'

export default function Audit({ items }) {
  return <div className="page"><div className="page-head"><div className="eyebrow">CONTROL PLANE / TRACEABILITY</div><h2>Action audit log</h2><p>Operations initiated through the FastAPI control service are recorded separately from the network's fault events.</p></div><section className="panel"><SectionHead title="CONTROL ACTION HISTORY" detail={`${items.length} local audit records loaded`}/><div className="table-scroll"><table className="data-table"><thead><tr><th>TIME</th><th>ACTION</th><th>TARGET</th><th>OUTCOME</th><th>DETAIL</th></tr></thead><tbody>{items.map((item,i)=><tr key={`${item.timestamp}-${i}`}><td className="cell-mono">{prettyDate(item.timestamp)}</td><td className="cell-mono">{item.action}</td><td>{item.target}</td><td><Label tone={item.outcome === 'SUCCESS' ? 'good' : 'danger'}>{item.outcome}</Label></td><td className="cell-truncate">{item.detail || '—'}</td></tr>)}</tbody></table>{!items.length && <Empty text="No control actions have been recorded yet."/>}</div></section></div>
}
