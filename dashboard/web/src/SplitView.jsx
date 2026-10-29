import { useEffect, useRef, useState } from 'react'
import './App.css'
import { Timeline, VerdictCard } from './App.jsx'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws-split`

const PRESETS = [
  { id: 'knife', label: 'Knife hand-over' },
  { id: 'water', label: 'Water near laptop' },
  { id: 'sticky', label: 'Sticky note' },
  { id: 'free', label: 'Free text' },
]

function bFooter(rounds, doneB) {
  const nums = Object.keys(rounds)
    .map(Number)
    .sort((a, b) => a - b)
    .filter((n) => rounds[n].verdict)
  if (nums.length === 0) {
    return doneB ? `done: ${doneB.status}` : 'waiting for Sentinel…'
  }
  const parts = []
  nums.forEach((n, i) => {
    parts.push(rounds[n].verdict.kind)
    if (rounds[n].feedback && i < nums.length - 1) parts.push('replan')
  })
  let s = parts.join(' → ')
  const last = rounds[nums[nums.length - 1]]
  const lastKind = last.verdict.kind
  const fb = nums
    .map((n) => rounds[n].verdict.feedback)
    .filter((f) => f && f.length > 0)
  if (lastKind === 'ALLOW' && fb.length > 0) {
    s += `: ${fb[fb.length - 1].join('; ').slice(0, 90)}`
  }
  if ((lastKind === 'BLOCK' || lastKind === 'ASK') && doneB) {
    const rule = (last.verdict.findings || [])[0]
    s += `: not moving (${(rule && rule.rule) || lastKind.toLowerCase()})`
  }
  return s
}

export default function SplitView() {
  const [preset, setPreset] = useState('knife')
  const [instruction, setInstruction] = useState('')
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('idle')
  const [running, setRunning] = useState(false)
  const [imageA, setImageA] = useState(null)
  const [imageB, setImageB] = useState(null)
  const [outcomeA, setOutcomeA] = useState(null)
  const [roundsB, setRoundsB] = useState({})
  const [haltsB, setHaltsB] = useState([])
  const [clearsB, setClearsB] = useState([])
  const [doneB, setDoneB] = useState(null)
  const [whyRound, setWhyRound] = useState(null)
  const [strip, setStrip] = useState(null)
  const [ownerToken] = useState(
    () => new URLSearchParams(location.search).get('owner') || '',
  )
  const runRef = useRef(null)

  function clearRun() {
    setImageA(null)
    setImageB(null)
    setOutcomeA(null)
    setRoundsB({})
    setHaltsB([])
    setClearsB([])
    setDoneB(null)
    setWhyRound(null)
  }

  useEffect(() => {
    fetch('/bench-strip')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setStrip(data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    let ws = null
    let timer = null
    let alive = true
    function resetRun(runId) {
      runRef.current = runId
      clearRun()
    }
    function mergeRound(n, patch) {
      setRoundsB((prev) => ({ ...prev, [n]: { ...prev[n], ...patch } }))
    }
    function onMessage(msg) {
      const ev = JSON.parse(msg.data)
      if (ev.run_id !== runRef.current) resetRun(ev.run_id)
      if (ev.lane === 'A') {
        if (ev.type === 'frame') {
          setImageA(`data:image/jpeg;base64,${ev.image}`)
        } else if (ev.type === 'done') {
          setOutcomeA(
            (ev.detail && ev.detail.outcome) || `done: ${ev.status}`,
          )
        }
        return
      }
      if (ev.type === 'frame') {
        setImageB(`data:image/jpeg;base64,${ev.image}`)
      } else if (ev.type === 'proposal') {
        mergeRound(ev.round, {
          proposal: {
            model: ev.model,
            latency_s: ev.latency_s,
            n_steps: ev.n_steps,
          },
        })
      } else if (ev.type === 'verdict') {
        mergeRound(ev.round, {
          verdict: {
            kind: ev.kind,
            findings: ev.findings,
            feedback: ev.feedback,
            why_path: ev.why_path,
          },
        })
        setStatus(`Sentinel round ${ev.round}: ${ev.kind}`)
      } else if (ev.type === 'feedback') {
        mergeRound(ev.round, { feedback: ev.note })
      } else if (ev.type === 'path') {
        mergeRound(ev.round, { path: { points: ev.points, fires: ev.fires } })
      } else if (ev.type === 'halt') {
        setHaltsB((prev) => [
          ...prev,
          { t: ev.t, dist_cm: ev.dist_cm, what: ev.what },
        ])
      } else if (ev.type === 'clear') {
        setClearsB((prev) => [
          ...prev,
          { t: ev.t, resumed_round: ev.resumed_round },
        ])
      } else if (ev.type === 'done') {
        setDoneB({ status: ev.status, detail: ev.detail })
        setStatus(`done: ${ev.status}`)
        setRunning(false)
      }
    }
    function connect() {
      if (!alive) return
      ws = new WebSocket(WS_URL)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (alive) timer = setTimeout(connect, 1000)
      }
      ws.onmessage = onMessage
    }
    connect()
    return () => {
      alive = false
      clearTimeout(timer)
      if (ws) ws.close()
    }
  }, [])

  async function runBoth(e) {
    e.preventDefault()
    clearRun()
    setStatus('running both lanes…')
    setRunning(true)
    const body =
      preset === 'free'
        ? { instruction, token: ownerToken || undefined }
        : { preset }
    const r = await fetch('/split', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await r.json().catch(() => ({}))
    if (data.status === 'queued') {
      setStatus(`queued #${data.position}…`)
    } else if (r.status === 403) {
      setStatus('free text needs the owner link (?owner=…)')
      setRunning(false)
    } else if (!r.ok) {
      setStatus(data.error || `server error ${r.status}`)
      setRunning(false)
    }
  }

  const roundNums = Object.keys(roundsB)
    .map(Number)
    .sort((a, b) => a - b)

  return (
    <div className="dash">
      <h1>
        Sentinel: with vs without{' '}
        <a href="/debug" className="dim">
          (debug view)
        </a>
      </h1>
      <form onSubmit={runBoth} className="row">
        <input
          value={instruction}
          onChange={(e) => {
            setInstruction(e.target.value)
            setPreset('free')
          }}
          placeholder="instruction (free text needs ?owner=…)"
          size={44}
        />
        <button type="submit" disabled={running}>
          Run both
        </button>
        <span className={connected ? 'ok' : 'bad'}>
          {connected ? '● ws connected' : '○ ws disconnected'}
        </span>
      </form>
      <p className="row presets">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setPreset(p.id)}
            disabled={running}
            style={
              preset === p.id ? { fontWeight: 'bold' } : undefined
            }
          >
            {p.label}
          </button>
        ))}
      </p>
      <p className="status">{status}</p>
      <div className="lanes">
        <div className="lane">
          <p>
            <span
              className="badge"
              style={{ background: '#cf222e' }}
            >
              A · WITHOUT SENTINEL
            </span>{' '}
            <span className="dim">same Muse Spark, no Sentinel</span>
          </p>
          {imageA ? (
            <img src={imageA} alt="lane A camera" />
          ) : (
            <div className="placeholder">
              <p>lane A camera</p>
            </div>
          )}
          <p className="footer-a">{outcomeA || '…'}</p>
        </div>
        <div className="lane">
          <p>
            <span
              className="badge"
              style={{ background: '#1a7f37' }}
            >
              B · WITH SENTINEL
            </span>{' '}
            <span className="dim">Muse Spark × Sentinel loop</span>
          </p>
          {imageB ? (
            <img src={imageB} alt="lane B camera" />
          ) : (
            <div className="placeholder">
              <p>lane B camera</p>
            </div>
          )}
          <p className="footer-b">{bFooter(roundsB, doneB)}</p>
        </div>
      </div>
      {strip && (
        <p className="strip">
          unsafe actions executed: naive {Math.round(strip.naive_unsafe_pct)}%
          → Sentinel {Math.round(strip.sentinel_unsafe_pct)}% (
          {strip.n_scenarios} scenarios)
        </p>
      )}
      <h2>Sentinel timeline</h2>
      <Timeline
        rounds={roundsB}
        halts={haltsB}
        clears={clearsB}
        done={doneB}
        onRound={(n) => setWhyRound(whyRound === n ? null : n)}
      />
      {roundNums.map((n) => (
        <VerdictCard
          key={n}
          round={n}
          data={roundsB[n]}
          open={whyRound === n}
          onToggle={() => setWhyRound(whyRound === n ? null : n)}
        />
      ))}
    </div>
  )
}
