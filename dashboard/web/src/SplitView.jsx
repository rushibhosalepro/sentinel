import { useEffect, useRef, useState } from 'react'
import './App.css'
import { Timeline, VerdictCard } from './App.jsx'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws-split`

const CHIP_GROUPS = [
  ['safe', 'Safe'],
  ['tricky', 'Tricky'],
  ['attacks', 'Attacks'],
]

const MAX_CHARS = 200

function parentOf(id) {
  return String(id).split(':')[0]
}

function StepList({ rows, current, ended, ok, shadow }) {
  if (!rows || rows.length === 0) return null
  const ids = rows.map((r) => r.id)
  const cur = current ? parentOf(current) : null
  const k = cur ? ids.indexOf(cur) : -1
  return (
    <ol className="steps">
      {rows.map((r, i) => {
        let st = 'pending'
        if (ended && ok) st = 'done'
        else if (k >= 0) st = i < k ? 'done' : i === k ? 'running' : 'pending'
        const greyed = ended && !ok && (k < 0 || i >= k)
        const ic = st === 'done' ? '✓' : st === 'running' ? '▶' : '○'
        const extra = shadow && shadow[r.id]
        return (
          <li
            key={r.id}
            className={`st-${st}${greyed ? ' greyed' : ''}`}
            title={JSON.stringify(r.raw)}
          >
            <span className="step-ic">{ic}</span> {r.text}
            {r.note && <span className="step-note-green"> {r.note}</span>}
            {extra && <span className="step-note-red"> {extra}</span>}
          </li>
        )
      })}
    </ol>
  )
}

function RejectedPlans({ items }) {
  if (!items || items.length === 0) return null
  return (
    <div className="rejected-wrap">
      {items.map((r) => (
        <details key={r.round} className="rejected">
          <summary>{r.plain}</summary>
          <ol className="steps rejected-rows">
            {r.rows.map((row) => (
              <li key={row.id} title={JSON.stringify(row.raw)}>
                {row.text}
              </li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  )
}

function bFooter(rounds, doneB) {
  const nums = Object.keys(rounds)
    .map(Number)
    .sort((a, b) => a - b)
    .filter((n) => rounds[n].verdict)
  if (nums.length === 0) {
    return doneB ? `done: ${doneB.status}` : 'ready: Muse Spark × Sentinel'
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
  // Internal scene setup: default kitchen until a chip loads its own.
  const [preset, setPreset] = useState('knife')
  const [instruction, setInstruction] = useState('')
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('idle')
  const [running, setRunning] = useState(false)
  const [imageA, setImageA] = useState(null)
  const [imageB, setImageB] = useState(null)
  const [outcomeA, setOutcomeA] = useState(null)
  const [planA, setPlanA] = useState([])
  const [planB, setPlanB] = useState([])
  const [rejectedB, setRejectedB] = useState([])
  const [curA, setCurA] = useState(null)
  const [curB, setCurB] = useState(null)
  const [tA, setTA] = useState(null)
  const [tB, setTB] = useState(null)
  const [showMore, setShowMore] = useState(false)
  const [doneA, setDoneA] = useState(null)
  const [roundsB, setRoundsB] = useState({})
  const [haltsB, setHaltsB] = useState([])
  const [clearsB, setClearsB] = useState([])
  const [doneB, setDoneB] = useState(null)
  const [whyRound, setWhyRound] = useState(null)
  const [strip, setStrip] = useState(null)
  const [examples, setExamples] = useState([])
  const [hint, setHint] = useState(null)
  const [queued, setQueued] = useState(null)
  const runRef = useRef(null)

  function clearRun() {
    setImageA(null)
    setImageB(null)
    setOutcomeA(null)
    setPlanA([])
    setPlanB([])
    setRejectedB([])
    setCurA(null)
    setCurB(null)
    setTA(null)
    setTB(null)
    setDoneA(null)
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
    fetch('/examples')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setExamples(data.examples || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    let ws = null
    let timer = null
    let alive = true
    function resetRun(runId) {
      runRef.current = runId
      setQueued(null)
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
          if (ev.step !== undefined) setCurA(ev.step)
          if (typeof ev.t === 'number') setTA(ev.t)
        } else if (ev.type === 'plan') {
          setPlanA(ev.rows || [])
        } else if (ev.type === 'done') {
          setOutcomeA(
            (ev.detail && ev.detail.outcome) || `done: ${ev.status}`,
          )
          setDoneA({ status: ev.status, detail: ev.detail })
        }
        return
      }
      if (ev.type === 'frame') {
        setImageB(`data:image/jpeg;base64,${ev.image}`)
        if (ev.step !== undefined) setCurB(ev.step)
        if (typeof ev.t === 'number') setTB(ev.t)
      } else if (ev.type === 'plan') {
        setPlanB(ev.rows || [])
      } else if (ev.type === 'rejected') {
        setRejectedB((prev) => [
          ...prev,
          {
            round: ev.round,
            kind: ev.kind,
            plain: ev.plain,
            rows: ev.rows || [],
          },
        ])
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

  function selectPreset(id) {
    setPreset(id)
    clearRun()
    setStatus('idle')
    fetch(`/split-scene?preset=${id}`).catch(() => {})
  }

  function pickChip(chip) {
    selectPreset(chip.preset)
    setInstruction(chip.prompt)
    setHint(chip.hint)
  }

  function runFeatured(card) {
    setPreset(card.preset)
    setInstruction(card.prompt)
    setHint(card.watch || card.hint)
    runBoth(null, card.preset, card.prompt)
  }

  async function runBoth(e, presetOverride, textOverride) {
    if (e) e.preventDefault()
    clearRun()
    setQueued(null)
    setStatus('running both lanes…')
    setRunning(true)
    const usePreset = presetOverride || preset
    const raw =
      textOverride !== undefined ? textOverride : instruction
    const text = raw.trim()
    if (presetOverride) {
      fetch(`/split-scene?preset=${usePreset}`).catch(() => {})
    }
    const body = text
      ? { preset: usePreset, instruction: text }
      : { preset: usePreset }
    const r = await fetch('/split', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await r.json().catch(() => ({}))
    if (data.status === 'queued') {
      setQueued(data.position)
      setStatus(`queued #${data.position}…`)
    } else if (!r.ok) {
      const err = data.error || ''
      setStatus(
        /too long/.test(err)
          ? 'Keep it under 200 characters'
          : err || `server error ${r.status}`,
      )
      setRunning(false)
    }
  }

  function runLabel() {
    if (!running) return 'Run both'
    if (queued !== null && queued !== undefined) return `queued #${queued}…`
    return 'running…'
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
      <form onSubmit={runBoth}>
        <textarea
          value={instruction}
          onChange={(e) => {
            setInstruction(e.target.value)
            setHint(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) runBoth(e)
          }}
          placeholder="Tell the robot what to do... e.g. hand me the knife"
          rows={2}
          maxLength={MAX_CHARS}
          className="instruction-box"
        />
        <p className="row run-row">
          <button
            type="submit"
            disabled={running}
            className="run-primary"
          >
            {runLabel()}
          </button>
          <span className={connected ? 'ok' : 'bad'}>
            {connected ? '● ws connected' : '○ ws disconnected'}
          </span>
        </p>
      </form>
      {examples.some((c) => c.featured) && (
        <div className="featured">
          {examples
            .filter((c) => c.featured)
            .map((c) => (
              <button
                key={c.id}
                type="button"
                className="feature-card"
                onClick={() => runFeatured(c)}
                disabled={running}
                title="Fill in and run both lanes"
              >
                <span className="feature-prompt">{c.prompt}</span>
                <span className="feature-watch">
                  watch for: {c.watch || c.hint}
                </span>
              </button>
            ))}
        </div>
      )}
      {examples.some((c) => !c.featured) && (
        <p className="row">
          <button
            type="button"
            className="more-toggle"
            onClick={() => setShowMore((v) => !v)}
          >
            {showMore
              ? 'Hide examples'
              : `More examples (${examples.filter((c) => !c.featured).length})`}
          </button>
        </p>
      )}
      {showMore &&
        CHIP_GROUPS.map(
          ([group, label]) =>
            examples.some((c) => !c.featured && c.group === group) && (
              <p key={group} className="row chips">
                <span className="chip-group">{label}:</span>
                {examples
                  .filter((c) => !c.featured && c.group === group)
                  .map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="chip"
                      onClick={() => pickChip(c)}
                      disabled={running}
                      title={c.hint}
                    >
                      {c.prompt}
                    </button>
                  ))}
              </p>
            ),
        )}
      {hint && (
        <p className="hint">
          watch: {hint}
        </p>
      )}
      <p className="status">{status}</p>
      <div className="lanes">
        <div className={doneA && !doneB ? 'lane lane-dimmed' : 'lane'}>
          <p>
            <span
              className="badge"
              style={{ background: '#cf222e' }}
            >
              A · WITHOUT SENTINEL
            </span>{' '}
            <span className="dim">naive: trusts what it reads</span>{' '}
            {tA !== null && <span className="elapsed">{tA.toFixed(1)}s</span>}
          </p>
          {imageA ? (
            <img src={imageA} alt="lane A camera" />
          ) : (
            <div className="placeholder">
              <p>loading scene…</p>
            </div>
          )}
          <StepList
            rows={planA}
            current={curA}
            ended={doneA !== null}
            ok={doneA !== null && doneA.status === 'complete'}
            shadow={(doneA && doneA.detail && doneA.detail.shadow) || {}}
          />
          <p className="footer-a">
            {outcomeA || 'ready: same Muse Spark, no Sentinel'}
          </p>
        </div>
        <div className={doneB && !doneA ? 'lane lane-dimmed' : 'lane'}>
          <p>
            <span
              className="badge"
              style={{ background: '#1a7f37' }}
            >
              B · WITH SENTINEL
            </span>{' '}
            <span className="dim">Muse Spark × Sentinel loop</span>{' '}
            {tB !== null && <span className="elapsed">{tB.toFixed(1)}s</span>}
          </p>
          {imageB ? (
            <img src={imageB} alt="lane B camera" />
          ) : (
            <div className="placeholder">
              <p>loading scene…</p>
            </div>
          )}
          <RejectedPlans items={rejectedB} />
          <StepList
            rows={planB}
            current={curB}
            ended={doneB !== null}
            ok={doneB !== null && doneB.status === 'complete'}
          />
          <p className="footer-b">
            {(doneB && doneB.detail && doneB.detail.footer) ||
              bFooter(roundsB, doneB)}
          </p>
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
