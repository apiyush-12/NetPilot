import React, { useRef, useState } from 'react'
import { AlertTriangle, Check, Download, FileUp, KeyRound, LockKeyhole, RotateCcw, Settings2, ShieldCheck } from 'lucide-react'
import { Label, SectionHead } from '../components/Chrome.jsx'
import { DEFAULT_SETTINGS, normalizeSettings } from '../lib/settings.js'
import './settings.css'
import './themes.css'

function SettingRow({ label, description, children, last = false }) {
  return <div className={`setting-row${last ? ' setting-row-last' : ''}`}>
    <div className="setting-copy"><strong>{label}</strong><p>{description}</p></div>
    <div className="setting-value">{children}</div>
  </div>
}
function SettingSelect({ value, onChange, choices, label }) {
  return <select className="select-input setting-select" value={value} aria-label={label} onChange={e => onChange(e.target.value)}>
    {choices.map(([id, text]) => <option key={id} value={id}>{text}</option>)}
  </select>
}
function SettingSwitch({ checked, onChange, label }) {
  return <label className="setting-toggle-label"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} aria-label={label}/><span className="setting-switch-track" aria-hidden="true"/><span className="setting-switch-caption">{checked ? 'ENABLED' : 'DISABLED'}</span></label>
}
const THEME_OPTIONS = [
  ['dark', 'Graphite / default'],
  ['midnight', 'Midnight / deep black'],
  ['carbon', 'Carbon Steel / charcoal'],
  ['navy', 'Command Navy / blue-gray'],
  ['terminal', 'Terminal Green / classic NOC'],
  ['industrial', 'Industrial Amber / warm graphite'],
  ['copper', 'Copper / dark orange'],
  ['light', 'Cloud White / professional light']
]
const INTERVAL_LABEL = value => value === 0 ? 'Manual only' : `Every ${value} seconds`

export default function Settings({ settings, onChange, onReplace, onLock, onUnlock, tokenLoaded, backendOnline }) {
  const [feedback, setFeedback] = useState('')
  const importRef = useRef(null)
  const change = (key, value) => { onChange(key, value); setFeedback('Preferences saved in this browser.') }
  const exportPreferences = () => {
    const blob = new Blob([JSON.stringify({ version: 1, settings }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'netpilot-ui-preferences.json'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    setFeedback('Exported UI preferences. No tokens or AWS credentials included.')
  }
  const importPreferences = async event => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      if (file.size > 32768) throw new Error('File exceeds the 32 KB preference limit.')
      const json = JSON.parse(await file.text())
      if (!json || typeof json !== 'object' || !json.settings || typeof json.settings !== 'object' || Array.isArray(json.settings)) throw new Error('Invalid NetPilot preference file.')
      onReplace(normalizeSettings(json.settings))
      setFeedback('UI preferences imported and applied.')
    } catch (error) { setFeedback(`Could not import preferences: ${error.message}`) }
  }
  const reset = () => {
    if (!window.confirm('Reset UI preferences to defaults? This does not change Docker, AWS, agent configuration or your control token.')) return
    onReplace({ ...DEFAULT_SETTINGS })
    setFeedback('UI preferences restored to defaults.')
  }

  return <div className="page settings-page">
    <div className="page-head"><div className="eyebrow">OPERATIONS CONSOLE / LOCAL PREFERENCES</div><h2>Settings</h2>
      <p>Customize how the console looks, polls data and presents alerts. These settings apply immediately and are saved locally in this browser.</p>
    </div>
    <div className="settings-main">
      <section className="panel"><SectionHead title="01 / APPEARANCE" detail="Display preferences for the operations workspace"/>
        <SettingRow label="Console theme" description="Choose a professional console palette. All options keep the compact, non-Bento layout.">
          <div className="theme-picker"><SettingSelect label="Console theme" value={settings.theme} onChange={v => change('theme', v)} choices={THEME_OPTIONS}/><div className={`theme-preview theme-preview-${settings.theme}`} aria-label={`Theme preview: ${THEME_OPTIONS.find(([id]) => id === settings.theme)?.[1] || settings.theme}`}><span className="theme-preview-rail">NETPILOT</span><span className="theme-preview-screen">ROUTER A / ONLINE</span><span className="theme-preview-light"/></div></div>
        </SettingRow>
        <SettingRow label="Status accent" description="Changes navigation selection, control highlights and focus indicators.">
          <div className="settings-accent-list" role="group" aria-label="Console accent color">{[['teal','Teal'],['blue','Blue'],['amber','Amber']].map(([id,label]) => <button key={id} className={`settings-accent-option ${settings.accent === id ? 'active' : ''}`} type="button" onClick={() => change('accent', id)} aria-pressed={settings.accent === id}><span className={`settings-swatch swatch-${id}`}/>{label}{settings.accent === id && <Check size={13}/>}</button>)}</div>
        </SettingRow>
        <SettingRow label="Information density" description="Compact reduces table rows and control spacing; comfortable improves readability.">
          <SettingSelect label="Information density" value={settings.density} onChange={v => change('density', v)} choices={[["comfortable","Comfortable"],["compact","Compact / NOC"]]}/>
        </SettingRow>
        <SettingRow label="Text size" description="Increase the main console text for easier reading." last>
          <SettingSelect label="Text size" value={settings.textScale} onChange={v => change('textScale', v)} choices={[["normal","Standard"],["large","Larger"]]}/>
        </SettingRow>
      </section>

      <section className="panel"><SectionHead title="02 / LIVE DATA" detail="Changes how often the browser fetches data; it does not change NetPilot's 5-second agent probe interval"/>
        <SettingRow label="Network status polling" description="Reads Docker service status, active routes and connectivity via FastAPI.">
          <SettingSelect label="Network status polling" value={settings.statusRefresh} onChange={v => change('statusRefresh', Number(v))} choices={[0,5,10,30].map(n=>[n, INTERVAL_LABEL(n)])}/>
        </SettingRow>
        <SettingRow label="Incidents and process logs" description="Refreshes the local incident register and controller/forwarder console output.">
          <SettingSelect label="Incident and log polling" value={settings.activityRefresh} onChange={v => change('activityRefresh', Number(v))} choices={[0,8,15,30].map(n=>[n, INTERVAL_LABEL(n)])}/>
        </SettingRow>
        <SettingRow label="Live event stream" description="Maintains an SSE connection to events.jsonl for updates without polling.">
          <SettingSwitch label="Live event stream" checked={settings.streamEnabled} onChange={v => change('streamEnabled', v)}/>
        </SettingRow>
        <SettingRow label="Cloud Events refresh" description="Refreshes the newest DynamoDB scan page while Cloud Events is open. Cloud reads may incur AWS charges.">
          <SettingSelect label="Cloud Events refresh" value={settings.cloudEventsRefresh} onChange={v => change('cloudEventsRefresh', Number(v))} choices={[0,30,60,120].map(n=>[n, INTERVAL_LABEL(n)])}/>
        </SettingRow>
        <SettingRow label="AWS health refresh" description="The AWS Operations page refreshes SQS/Lambda/DynamoDB summaries only while open.">
          <SettingSelect label="AWS health refresh" value={settings.cloudStatusRefresh} onChange={v => change('cloudStatusRefresh', Number(v))} choices={[0,60,120].map(n=>[n, INTERVAL_LABEL(n)])} />
        </SettingRow>
        <SettingRow label="First page on startup" description="Chosen page opens when the browser reloads. The control token will still need to be unlocked." last>
          <SettingSelect label="First page" value={settings.landingPage} onChange={v => change('landingPage', v)} choices={[["operations","Control Center"],["monitoring","Monitoring"],["recovery","Recovery Tracker"],["events","Event Logs"],["cloud","AWS Operations"],["cloud-events","Cloud Events"],["audit","Action Audit"],["settings","Settings"]]}/>
        </SettingRow>
      </section>

      <section className="panel"><SectionHead title="03 / ALERTS AND TIME" detail="Notification display and timestamp preferences"/>
        <SettingRow label="New-incident alerts" description="Shows an in-app alert when a new INCIDENT_CREATED event arrives over the live stream.">
          <SettingSwitch label="New incident alerts" checked={settings.incidentAlerts} onChange={v=>change('incidentAlerts',v)}/>
        </SettingRow>
        <SettingRow label="Recovery notifications" description="Shows an in-app notice when INCIDENT_RESOLVED arrives over the live stream.">
          <SettingSwitch label="Recovery notifications" checked={settings.recoveryAlerts} onChange={v=>change('recoveryAlerts',v)}/>
        </SettingRow>
        <SettingRow label="Timestamp timezone" description="Choose local system time or UTC for dates in logs and incident details.">
          <SettingSelect label="Timestamp timezone" value={settings.clockZone} onChange={v=>change('clockZone',v)} choices={[["local","My local timezone"],["utc","UTC"]]}/>
        </SettingRow>
        <SettingRow label="Clock format" description="Controls the top-bar clock and formatted event timestamps." last>
          <SettingSelect label="Clock format" value={settings.clockFormat} onChange={v=>change('clockFormat',v)} choices={[["24h","24-hour"],["12h","12-hour"]]}/>
        </SettingRow>
      </section>

      <section className="panel"><SectionHead title="04 / ACCESS AND SAFEGUARDS" detail="Local development security and control behavior"/>
        <div className="settings-security">
          <div className="settings-security-line"><span><ShieldCheck size={16}/> Backend connection</span><Label tone={backendOnline ? 'good' : 'danger'}>{backendOnline ? 'ONLINE' : 'OFFLINE'}</Label></div>
          <div className="settings-security-line"><span><KeyRound size={16}/> Control authorization</span><Label tone={tokenLoaded ? 'good' : 'warn'}>{tokenLoaded ? 'TOKEN LOADED' : 'LOCKED'}</Label></div>
          <div className="settings-security-line"><span><ShieldCheck size={16}/> Disruptive-action confirmations</span><Label tone="good">ALWAYS REQUIRED</Label></div>
          <p className="settings-security-note"><AlertTriangle size={15}/> The browser stores only UI preferences. The control token stays in memory, is never exported, and is validated by FastAPI. Settings cannot disable server-side authorization or safeguards.</p>
          <div className="settings-inline-actions"><button className="button button-quiet" type="button" onClick={onUnlock}><KeyRound size={14}/> {tokenLoaded ? 'CHANGE TOKEN' : 'UNLOCK CONTROLS'}</button><button className="button button-danger-outline" type="button" onClick={onLock} disabled={!tokenLoaded}><LockKeyhole size={14}/> LOCK CONTROLS</button></div>
        </div>
      </section>

      <section className="panel"><SectionHead title="05 / PREFERENCE BACKUP" detail="Export, import and reset non-sensitive browser settings"/>
        <div className="settings-preference-actions">
          <button className="button button-quiet" type="button" onClick={exportPreferences}><Download size={14}/> EXPORT JSON</button>
          <button className="button button-quiet" type="button" onClick={() => importRef.current?.click()}><FileUp size={14}/> IMPORT JSON</button>
          <input ref={importRef} type="file" hidden accept=".json,application/json" onChange={importPreferences} aria-label="Import preferences JSON"/>
          <button className="button button-danger-outline" type="button" onClick={reset}><RotateCcw size={14}/> RESET DEFAULTS</button>
          {feedback && <div className="settings-feedback" role="status"><Settings2 size={14}/>{feedback}</div>}
        </div>
      </section>
    </div>
    <div className="foot-note">Settings are saved per browser profile. They do not edit Docker routes, NetPilot recovery policies, IAM permissions or AWS infrastructure. Manual refresh always remains available.</div>
  </div>
}
