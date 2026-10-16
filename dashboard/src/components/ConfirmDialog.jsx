import React from 'react'
import { AlertTriangle, X } from 'lucide-react'

export default function ConfirmDialog({ request, onCancel, onConfirm, busy }) {
  if (!request) return null
  return <div className="modal-shade" role="presentation" onMouseDown={e => e.target === e.currentTarget && !busy && onCancel()}>
    <div role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="modal confirm-modal">
      <div className="modal-bar"><strong>OPERATION CONFIRMATION</strong><button className="icon-button" onClick={onCancel} disabled={busy} aria-label="Close"><X size={18}/></button></div>
      <div className="modal-body"><div className="warning-icon"><AlertTriangle size={26}/></div><h2 id="confirm-title">{request.title}</h2>
        <p>{request.description}</p><div className="command-line">POST {request.path}</div>
        <div className="modal-actions"><button className="button button-quiet" onClick={onCancel} disabled={busy}>CANCEL</button><button className={`button ${request.destructive ? 'button-danger' : 'button-accent'}`} onClick={onConfirm} disabled={busy}>{busy ? 'EXECUTING…' : 'CONFIRM ACTION'}</button></div>
      </div>
    </div>
  </div>
}

export function TokenDialog({ open, onClose, onSave, value, setValue }) {
  if (!open) return null
  return <div className="modal-shade" role="presentation" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <form role="dialog" aria-modal="true" aria-labelledby="token-title" className="modal" onSubmit={e => { e.preventDefault(); onSave() }}>
      <div className="modal-bar"><strong>LOCAL CONTROL ACCESS</strong><button type="button" className="icon-button" onClick={onClose} aria-label="Close"><X size={18}/></button></div>
      <div className="modal-body"><h2 id="token-title">Unlock control commands</h2><p>Paste the temporary <code>NETPILOT_CONTROL_TOKEN</code> from the PowerShell session running FastAPI. It is held in browser memory only, and is never written to a frontend file or browser storage.</p>
        <label htmlFor="token-input" className="field-label">X-NetPilot-Token</label>
        <input id="token-input" type="password" autoComplete="off" autoFocus className="text-input" value={value} onChange={e => setValue(e.target.value)} placeholder="Paste local control token" />
        <p className="micro-note">A loaded token is not proof of authorization; the backend validates it when you execute an action. Keep the API on 127.0.0.1.</p>
        <div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>CANCEL</button><button type="submit" className="button button-accent">USE TOKEN</button></div>
      </div>
    </form>
  </div>
}
