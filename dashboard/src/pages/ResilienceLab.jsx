import React, { useEffect, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  RefreshCw,
  RotateCcw
} from 'lucide-react'
import { apiGet } from '../lib/api.js'
import { Empty, Label, SectionHead } from '../components/Chrome.jsx'
import './resilience-lab.css'

const seconds = value =>
  typeof value === 'number'
    ? `${(value / 1000).toFixed(2)} s`
    : '—'

const dateText = value =>
  value ? new Date(value).toLocaleString() : '—'

const readable = value =>
  String(value || 'UNKNOWN').replaceAll('_', ' ')

export default function ResilienceLab() {
  const [history, setHistory] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [replay, setReplay] = useState(null)

  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [refresh, setRefresh] = useState(0)

  const [historyLoading, setHistoryLoading] = useState(false)
  const [replayLoading, setReplayLoading] = useState(false)
  const [error, setError] = useState('')

  const [sourceFilter, setSourceFilter] = useState('all')

  // Load controlled experiments and observed incidents.
  useEffect(() => {
    let active = true
    setHistoryLoading(true)
    setError('')

    apiGet('/api/resilience/history?limit=50')
      .then(data => {
        if (!active) return

        const items = Array.isArray(data.items)
          ? data.items
          : []

        setHistory(items)
      })
      .catch(err => {
        if (active) setError(err.message)
      })
      .finally(() => {
        if (active) setHistoryLoading(false)
      })

    return () => { active = false }
  }, [refresh])

  // Keep selection inside the active history filter.
  useEffect(() => {
    const visible = history.filter(
      item => sourceFilter === 'all' || item.kind === sourceFilter
    )
    setSelectedId(previous =>
      visible.some(item => item.id === previous)
        ? previous
        : (visible[0]?.id || '')
    )
  }, [history, sourceFilter])

  // Fetch the selected experiment or observed incident's timeline.
  useEffect(() => {
    if (!selectedId) {
      setReplay(null)
      setReplayLoading(false)
      setPlaying(false)
      return
    }

    const controller = new AbortController()

    setReplayLoading(true)
    setReplay(null)
    setStep(0)
    setPlaying(false)
    setError('')

    apiGet(
      selectedId.startsWith('incident:')
        ? `/api/resilience/incidents/${selectedId.slice(9)}/replay`
        : `/api/resilience/experiments/${selectedId.slice(11)}/replay`,
      controller.signal
    )
      .then(data => {
        if (!controller.signal.aborted) setReplay(data)
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          setError(err.message)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setReplayLoading(false)
        }
      })

    return () => controller.abort()
  }, [selectedId, refresh])

  const timeline = replay?.timeline || []
  const selectedEvent = timeline[step] || null
  const lastStep = timeline.length - 1
  const isPlaying =
    playing && timeline.length > 1 && step < lastStep

  // Automatic playback moves through recorded steps.
  useEffect(() => {
    if (!isPlaying) return

    const timer = window.setTimeout(() => {
      setStep(current => Math.min(current + 1, lastStep))
    }, 1400)

    return () => window.clearTimeout(timer)
  }, [isPlaying, step, lastStep])

  function togglePlayback() {
    if (isPlaying) {
      setPlaying(false)
      return
    }

    if (step >= lastStep) setStep(0)
    setPlaying(true)
  }

  function goToStep(index) {
    setPlaying(false)
    setStep(Math.max(0, Math.min(index, lastStep)))
  }

  const metrics = replay?.metrics || {}
  const visibleHistory = history.filter(
    item => sourceFilter === 'all' || item.kind === sourceFilter
  )
  const metricRows = replay?.experiment_id
    ? [
        ['FIRST FAILURE', metrics.first_failure_ms],
        ['INCIDENT CREATED', metrics.incident_created_ms],
        ['TOTAL RECOVERY', metrics.total_recovery_ms],
        ['ROUTE CHANGE', metrics.route_change_ms]
      ]
    : [
        ['INCIDENT RECOVERY', metrics.incident_recovery_ms],
        ['ROUTE CHANGE', metrics.route_change_ms]
      ]

  return (
    <div className="page resilience-lab">
      <div className="page-head">
        <div className="eyebrow">
          NETWORK RESILIENCE / HISTORICAL ANALYSIS
        </div>
        <h2>Resilience Lab</h2>
        <p>
          Explore recorded network fault experiments,
          recovery performance and step-by-step incident replay.
          Playback never modifies the live Docker network.
        </p>
      </div>

      <div className="resilience-toolbar">
        <div>
          <strong>INCIDENT TIME MACHINE</strong>
          <span>Controlled experiments and observed incident evidence</span>
        </div>

        <div className="button-row">
          <Label tone="good">READ ONLY</Label>

          <button
            className="button button-quiet"
            type="button"
            onClick={() => {
              setPlaying(false)
              setRefresh(value => value + 1)
            }}
          >
            <RefreshCw size={14} />
            REFRESH
          </button>
        </div>
      </div>

      {error && (
        <div className="diagnostic-error" role="alert">
          {error}
        </div>
      )}

      <div className="resilience-layout">

        {/* Unified resilience history */}
        <section className="panel resilience-history">
          <SectionHead
            title="RESILIENCE HISTORY"
            detail={`${visibleHistory.length} records`}
            right={
              <select
                className="select-input"
                value={sourceFilter}
                aria-label="Resilience history filter"
                onChange={event => setSourceFilter(event.target.value)}
              >
                <option value="all">All Records</option>
                <option value="experiment">Experiments</option>
                <option value="observed">Observed Incidents</option>
              </select>
            }
          />

          <div className="resilience-history-list">
            {visibleHistory.map(item => (
              <button
                type="button"
                key={item.id}
                className={
                  'resilience-history-item ' +
                  (selectedId === item.id
                    ? 'active'
                    : '')
                }
                onClick={() => setSelectedId(item.id)}
              >
                <div className="resilience-history-top">
                  <strong>{readable(item.scenario || item.fault_type)}</strong>

                  <Label
                    tone={
                      ['RECOVERED', 'RESOLVED'].includes(item.status)
                        ? 'good'
                        : 'warn'
                    }
                  >
                    {item.status}
                  </Label>
                </div>

                <span>{dateText(item.timestamp)}</span>

                <small>
                  {item.kind === 'experiment'
                    ? 'CONTROLLED EXPERIMENT'
                    : 'UNLINKED OBSERVED INCIDENT'}
                  {' / '}
                  ID: {String(item.experiment_id || item.incident_id).slice(0, 13)}
                </small>
              </button>
            ))}

            {!visibleHistory.length && !historyLoading && (
              <Empty text="No matching resilience history records." />
            )}

            {historyLoading && (
              <div className="resilience-note" role="status">
                Loading resilience history...
              </div>
            )}
          </div>
        </section>

        {/* Replay viewer */}
        <section className="panel resilience-viewer">
          <SectionHead
            title="INCIDENT REPLAY"
            detail={
              replay
                ? replay.experiment_id
                  ? `Experiment ${replay.experiment_id}`
                  : `Incident ${replay.incident_id}`
                : 'Select a history record'
            }
            right={<Label>HISTORY ONLY</Label>}
          />

          {replayLoading && (
            <div className="resilience-note" role="status">
              Loading recorded event timeline...
            </div>
          )}

          {replay && (
            <>
              <div className="resilience-summary">
                <div>
                  <span>FAULT / SCENARIO</span>
                  <strong>{readable(replay.scenario || replay.fault_type)}</strong>
                </div>

                <div>
                  <span>OUTCOME</span>
                  <strong>{readable(replay.status)}</strong>
                </div>

                <div>
                  <span>INCIDENT ID</span>
                  <strong>
                    {replay.incident_id
                      ? replay.incident_id.slice(0, 13)
                      : 'NOT MATCHED'}
                  </strong>
                </div>
              </div>

              <div className="resilience-metrics">
                {metricRows.map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{seconds(value)}</strong>
                  </div>
                ))}
              </div>

              <div className="resilience-playback">
                <div className="resilience-playback-heading">
                  <strong>EVENT PLAYBACK</strong>
                  <span>
                    {timeline.length
                      ? `${step + 1} / ${timeline.length}`
                      : '0 / 0'}
                  </span>
                </div>

                <div className="resilience-progress">
                  <div
                    style={{
                      width: timeline.length
                        ? `${((step + 1) / timeline.length) * 100}%`
                        : '0%'
                    }}
                  />
                </div>

                <div className="resilience-controls">
                  <button
                    className="button button-quiet"
                    onClick={() => goToStep(0)}
                    disabled={step === 0}
                  >
                    <RotateCcw size={14} />
                    RESET
                  </button>

                  <button
                    className="button button-quiet"
                    onClick={() => goToStep(step - 1)}
                    disabled={step === 0}
                    aria-label="Previous event"
                  >
                    <ChevronLeft size={16} />
                  </button>

                  <button
                    className="button button-accent"
                    onClick={togglePlayback}
                    disabled={timeline.length < 2}
                  >
                    {isPlaying
                      ? <Pause size={14} />
                      : <Play size={14} />}
                    {isPlaying
                      ? 'PAUSE'
                      : step >= lastStep ? 'REPLAY' : 'PLAY'}
                  </button>

                  <button
                    className="button button-quiet"
                    onClick={() => goToStep(step + 1)}
                    disabled={step >= lastStep}
                    aria-label="Next event"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>

              <div className="resilience-event-list">
                {timeline.map((item, index) => (
                  <button
                    type="button"
                    key={index}
                    className={
                      'resilience-event-item ' +
                      (step === index ? 'active' : '')
                    }
                    onClick={() => goToStep(index)}
                    aria-pressed={step === index}
                  >
                    <span className="resilience-event-number">
                      {String(index + 1).padStart(2, '0')}
                    </span>

                    <span className="resilience-event-name">
                      <strong>{item.label}</strong>
                      <small>{item.phase}</small>
                    </span>

                    <span className="resilience-event-time">
                      {seconds(item.elapsed_ms)}
                    </span>
                  </button>
                ))}
              </div>

              {selectedEvent && (
                <div className="resilience-event-detail">
                  <div className="resilience-detail-heading">
                    <strong>{selectedEvent.event}</strong>
                    <Label>
                      {selectedEvent.association === 'time_window'
                        ? 'APPROXIMATE MATCH'
                        : 'RECORDED EVIDENCE'}
                    </Label>
                  </div>

                  <table className="details-table">
                    <tbody>
                      <tr>
                        <th>Event time</th>
                        <td>{dateText(selectedEvent.timestamp)}</td>
                      </tr>
                      <tr>
                        <th>Elapsed</th>
                        <td>{seconds(selectedEvent.elapsed_ms)}</td>
                      </tr>
                      <tr>
                        <th>Source</th>
                        <td>{selectedEvent.source}</td>
                      </tr>
                      <tr>
                        <th>Association</th>
                        <td>{selectedEvent.association}</td>
                      </tr>

                      {Object.entries(
                        selectedEvent.details || {}
                      ).map(([key, value]) => (
                        <tr key={key}>
                          <th>{readable(key)}</th>
                          <td>
                            {typeof value === 'object'
                              ? JSON.stringify(value)
                              : String(value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="resilience-note">
                {replay.verified_recovery
                  ? 'Recovery is supported by matched controller events. This is not an independent live connectivity test.'
                  : 'A verified recovery could not be established from the matched controller events.'}
                {replay.truncated &&
                  ' This replay is truncated to 150 controller events.'}
              </div>
            </>
          )}

          {!replay && !replayLoading && (
            <Empty text="Choose a history record to view its replay." />
          )}
        </section>
      </div>
    </div>
  )
}