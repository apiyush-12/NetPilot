import React from 'react'
import { Cloud as CloudIcon, Database, Inbox, ShieldAlert, Zap } from 'lucide-react'
import { Label, SectionHead } from '../components/Chrome.jsx'
import { prettyDate } from '../lib/format.js'

const RESOURCES = [
  { id: 'sqs', label: 'SQS INCIDENT QUEUE', service: 'netpilot-incidents-dev', icon: Inbox },
  { id: 'dead_letter_queue', label: 'SQS DEAD-LETTER QUEUE', service: 'netpilot-incidents-dlq-dev', icon: ShieldAlert },
  { id: 'lambda', label: 'LAMBDA PROCESSOR', service: 'netpilot-incident-processor-dev', icon: Zap },
  { id: 'dynamodb', label: 'DYNAMODB EVENT TABLE', service: 'netpilot-events-dev', icon: Database },
  { id: 'dlq_alarm', label: 'CLOUDWATCH DLQ ALARM', service: 'netpilot-dlq-alert-dev', icon: CloudIcon }
]

function ResourceDetails({ id, data }) {
  if (!data) return null
  const flat = []
  if (id === 'sqs' || id === 'dead_letter_queue') {
    flat.push(['AVAILABLE', data.available_messages],['IN FLIGHT',data.in_flight_messages])
  } else if (id === 'lambda') flat.push(['STATE',data.State],['DEPLOY',data.LastUpdateStatus],['RUNTIME',data.Runtime])
  else if (id === 'dynamodb') {
    flat.push(['STATUS',data.Status])
    if (data.LiveItems !== null && data.LiveItems !== undefined) flat.push(['LIVE ITEMS',data.LiveItems])
    else if (data.CountLowerBound !== undefined) flat.push(['AT LEAST',data.CountLowerBound])
    else flat.push(['LIVE ITEMS','UNAVAILABLE'])
    flat.push(['DELAYED METADATA',data.ApproximateItems])
  }
  else if (id === 'dlq_alarm') flat.push(['STATE',data.State],['NAME',data.Name])
  return <div className="cloud-detail">{flat.map(([name,value])=><div key={name}><span>{name}</span><strong>{String(value ?? '—')}</strong></div>)}</div>
}

export default function Cloud({ cloud, cloudLoading, refreshCloud, setView }) {
  return <div className="page"><div className="page-head"><div className="eyebrow">CLOUD OPERATIONS / AWS</div><h2>AWS infrastructure status</h2><p>Read-only service state from your configured local AWS CLI credentials. AWS account secrets never enter the browser.</p></div>
    <section className="panel"><SectionHead title="CLOUD RESOURCE INVENTORY" detail={`AWS region: ${cloud?.region || 'ap-south-1'} · Last sample: ${prettyDate(cloud?.timestamp)}`} right={<button className="button button-accent" onClick={refreshCloud} disabled={cloudLoading}>{cloudLoading ? 'CHECKING…' : 'REFRESH CLOUD STATUS'}</button>}/>
      <div className="cloud-inventory-tools"><span>Live items are counted from DynamoDB scan pages; metadata updates can lag.</span><button className="button button-accent" onClick={() => setView('cloud-events')}>OPEN CLOUD EVENT EXPLORER →</button></div><div className="cloud-rows">{RESOURCES.map(({id,label,service,icon:Icon}) => {
        const resource = cloud?.resources?.[id]
        const condition = resource?.ok === true ? 'good' : resource?.ok === false ? 'danger' : 'neutral'
        return <div className="cloud-row" key={id}><div className="cloud-row-icon"><Icon size={19}/></div><div className="cloud-row-main"><div className="cloud-row-title"><strong>{label}</strong><Label tone={condition}>{resource?.ok === true ? 'RESPONDING' : resource?.ok === false ? 'ERROR' : 'NOT CHECKED'}</Label></div><div className="muted small-text">{service}</div>{resource?.error && <div className="diagnostic-error">{resource.error}</div>}<ResourceDetails id={id} data={resource?.data}/></div></div>
      })}</div>
    </section>
    <div className="foot-note">Cloud controls are intentionally read-only in this version. Changing IAM, queues, Lambda triggers or DynamoDB data requires dedicated scoped backend operations and confirmation safeguards; no unrestricted AWS console is exposed.</div>
  </div>
}
