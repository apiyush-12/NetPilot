import React from 'react'
import { Empty, Label } from './Chrome.jsx'
import { prettyDate, readableType, severityOf, shortId } from '../lib/format.js'

export default function EventTable({ items, maxRows, onIncident, selectedIncident }) {
  const rows = maxRows ? items.slice(0, maxRows) : items
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>TIME</th><th>EVENT</th><th>INCIDENT</th><th>DETAIL</th></tr></thead>
    <tbody>{rows.map((entry, i) => {
      const detail = entry.fault_type || entry.reason || entry.resolution || entry.target || entry.active_router || (entry.attempt ? `Attempt ${entry.attempt}` : '')
      return <tr key={entry.event_id || i} className={selectedIncident && selectedIncident === entry.incident_id ? 'row-selected' : ''}>
        <td className="cell-mono cell-time" title={prettyDate(entry.timestamp)}>{prettyDate(entry.timestamp)}</td>
        <td><Label tone={severityOf(entry.event)}>{readableType(entry.event)}</Label></td>
        <td className="cell-mono">{entry.incident_id ? <button className="text-button" onClick={() => onIncident?.(entry.incident_id)} title={entry.incident_id}>{shortId(entry.incident_id, 12)}</button> : <span className="muted">—</span>}</td>
        <td className="cell-truncate" title={String(detail)}>{detail || <span className="muted">—</span>}</td>
      </tr>
    })}</tbody></table>{!rows.length && <Empty text="No matching events recorded."/>}</div>
}
