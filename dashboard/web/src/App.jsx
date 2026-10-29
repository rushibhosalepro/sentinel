import { useEffect, useRef, useState } from 'react'
import './App.css'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`

// Display-only relation thresholds for the graph tab (not Sentinel's).
const NEAR_M = 0.25
const ABOVE_DZ = 0.05
const ABOVE_XY = 0.12
const GW = 460
const GH = 420
const GPAD = 34
const MIN_SEP_PX = 28

const KIND_COLORS = {
  ALLOW: '#1a7f37',
  ASK: '#b45309',
  BLOCK: '#cf222e',
  HALT: '#8250df',
  ERROR: '#6e7781',
}

function hazardColor(props) {
  if (props.includes('sharp')) return '#d1242f'
  if (props.includes('hot')) return '#e8590c'
  if (props.includes('medication')) return '#e67700'
  if (props.includes('liquid')) return '#1971c2'
  if (props.includes('electronic')) return '#495057'
  return '#adb5bd'
}

function dist3(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
}

function findThreshold(params) {
  if (!params || typeof params !== 'object') return null
  if (typeof params.within_cm === 'number') return params.within_cm
  for (const v of Object.values(params)) {
    const t = findThreshold(v)
    if (t !== null) return t
  }
  return null
}

function measuredLabel(w, people) {
  const rel = (w.relations || [])[0]
  const end = (id) =>
    people.includes(id) ? `${id}_hand` : id
  const p = w.predicates || {}
  const key =
    ['tip_cm', 'gap_cm'].find((k) => typeof p[k] === 'number') ||
    Object.keys(p).find((k) => k.endsWith('_cm'))
  const thr = findThreshold(w.params)
  if (rel && key && thr !== null) {
    return `${end(rel.subj)} → ${end(rel.obj)} ${p[key].toFixed(1)} cm < ${thr} cm`
  }
  const [k, v] = Object.entries(p)[0] || []
  const where =
    rel !== undefined ? `${end(rel.subj)} ${rel.rel} ${end(rel.obj)}: ` : ''
  return v !== undefined ? `${where}${k}=${JSON.stringify(v)}` : w.rule
}

function GraphTab({ graph, why, path }) {
  if (!graph) {
    return (
      <div className="placeholder tall">
        <p>loading scene...</p>
      </div>
    )
  }
  const nodes = []
  for (const [id, o] of Object.entries(graph.objects || {})) {
    nodes.push({ id, pos: o.pos, props: o.properties || [], person: false })
  }
  const people = Object.keys(graph.people || {})
  for (const pid of people) {
    const p = graph.people[pid]
    nodes.push({ id: `${pid} hand`, pos: p.hand, props: [], person: true })
    nodes.push({ id: `${pid} torso`, pos: p.torso, props: [], person: true })
  }
  const pts = path && path.points ? path.points : []
  const xs = [...nodes.map((n) => n.pos[0]), ...pts.map((p) => p[0])]
  const ys = [...nodes.map((n) => n.pos[1]), ...pts.map((p) => p[1])]
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const y0 = Math.min(...ys)
  const y1 = Math.max(...ys)
  const s = Math.min((GW - 2 * GPAD) / Math.max(x1 - x0, 1e-6),
    (GH - 2 * GPAD) / Math.max(y1 - y0, 1e-6))
  const X = (x) => GPAD + (x - x0) * s + (GW - 2 * GPAD - (x1 - x0) * s) / 2
  const Y = (y) => GH - GPAD - (y - y0) * s - (GH - 2 * GPAD - (y1 - y0) * s) / 2
  const laid = nodes.map((n) => ({ ...n, px: X(n.pos[0]), py: Y(n.pos[1]) }))
  for (let k = 0; k < 60; k++) {
    for (let i = 0; i < laid.length; i++) {
      for (let j = i + 1; j < laid.length; j++) {
        const dx = laid[j].px - laid[i].px
        const dy = laid[j].py - laid[i].py
        const d = Math.hypot(dx, dy)
        if (d >= MIN_SEP_PX) continue
        if (d < 1e-6) {
          laid[j].px += (j % 2 ? 1 : -1) * 2
          laid[j].py += ((j % 3) - 1) * 2
          continue
        }
        const push = (MIN_SEP_PX - d) / 2
        const ux = dx / d
        const uy = dy / d
        laid[i].px -= push * ux
        laid[i].py -= push * uy
        laid[j].px += push * ux
        laid[j].py += push * uy
      }
    }
  }
  const byId = Object.fromEntries(laid.map((n) => [n.id, n]))
  const edges = []
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]
      const b = nodes[j]
      const dz = Math.abs(a.pos[2] - b.pos[2])
      const dxy = Math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1])
      if (dz > ABOVE_DZ && dxy < ABOVE_XY) {
        const top = a.pos[2] > b.pos[2] ? a : b
        const bot = top === a ? b : a
        edges.push({ a: byId[top.id], b: byId[bot.id], rel: 'ABOVE' })
      } else if (dist3(a.pos, b.pos) < NEAR_M) {
        edges.push({ a: byId[a.id], b: byId[b.id], rel: 'NEAR' })
      }
    }
  }
  const whyEntries = (why || []).filter((w) => typeof w !== 'string')
  const hlNodes = new Set()
  const hlEdges = []
  whyEntries.forEach((w, wi) => {
    for (const r of w.relations || []) {
      for (const end of [r.subj, r.obj]) {
        if (byId[end]) hlNodes.add(end)
        if (people.includes(end)) {
          hlNodes.add(`${end} hand`)
          hlNodes.add(`${end} torso`)
        }
      }
      const a = byId[r.subj] || byId[`${r.subj} hand`]
      const b = byId[r.obj] || byId[`${r.obj} hand`]
      if (a && b) hlEdges.push({ a, b, label: measuredLabel(w, people), wi })
    }
  })
  const active = hlEdges.length > 0 || hlNodes.size > 0
  const faded = (id) => active && !hlNodes.has(id)
  const pathPx = pts.map(([x, y]) => [X(x), Y(y)])
  const firePx = ((path && path.fires) || []).map(([x, y]) => [X(x), Y(y)])
  return (
    <div>
      <svg className="graph" viewBox={`0 0 ${GW} ${GH}`}>
        {pathPx.length > 1 && (
          <polyline
            points={pathPx.map((p) => p.join(',')).join(' ')}
            className="pathline"
            opacity={active ? 0.3 : 1}
          />
        )}
        {firePx.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={4} className="fire" />
        ))}
        {pathPx.length > 0 && (
          <g>
            <rect
              x={pathPx[0][0] - 5} y={pathPx[0][1] - 5}
              width={10} height={10} className="gripper"
              transform={`rotate(45 ${pathPx[0][0]} ${pathPx[0][1]})`}
            />
            <text x={pathPx[0][0] + 8} y={pathPx[0][1]} className="grip-label">
              gripper
            </text>
          </g>
        )}
        {edges.map((e, i) => (
          <g
            key={i} className="edge"
            opacity={active && !hlNodes.has(e.a.id) && !hlNodes.has(e.b.id)
              ? 0.3
              : 1}
          >
            <title>{e.rel}</title>
            <line x1={e.a.px} y1={e.a.py} x2={e.b.px} y2={e.b.py} />
            <text x={(e.a.px + e.b.px) / 2} y={(e.a.py + e.b.py) / 2}>
              {e.rel}
            </text>
          </g>
        ))}
        {hlEdges.map((e, i) => (
          <g key={`h${i}`}>
            <line
              x1={e.a.px} y1={e.a.py} x2={e.b.px} y2={e.b.py}
              className="hledge"
            />
            <text
              x={(e.a.px + e.b.px) / 2} y={(e.a.py + e.b.py) / 2 + e.wi * 12}
              className="hedge-label"
            >
              {e.label}
            </text>
          </g>
        ))}
        {laid.map((n, i) => {
          const right = i % 2 === 0
          const lx = n.px + (right ? 8 : -8)
          const anchor = right ? 'start' : 'end'
          const hot = active && hlNodes.has(n.id)
          return (
            <g key={n.id} opacity={faded(n.id) ? 0.3 : 1}>
              {n.person ? (
                <rect
                  x={n.px - 5} y={n.py - 5}
                  width={10} height={10} className="person"
                />
              ) : (
                <circle cx={n.px} cy={n.py} r={5} fill={hazardColor(n.props)} />
              )}
              {hot && (
                <circle cx={n.px} cy={n.py} r={8} className="hotring" />
              )}
              <text x={lx} y={n.py + 4} textAnchor={anchor}>
                {n.id}
              </text>
              {!n.person &&
                n.props
                  .filter((p) =>
                    ['sharp', 'hot', 'liquid', 'electronic', 'medication'].includes(p),
                  )
                  .map((p, k) => (
                    <g key={p}>
                      <line
                        x1={n.px} y1={n.py}
                        x2={n.px + 8} y2={n.py + 12 + k * 12}
                        className="has"
                      />
                      <text
                        x={n.px + 10} y={n.py + 15 + k * 12}
                        className="has"
                      >
                        HAS {p}
                      </text>
                    </g>
                  ))}
            </g>
          )
        })}
      </svg>
      <p className="legend">
        <span style={{ color: '#d1242f' }}>● sharp</span>{' '}
        <span style={{ color: '#e8590c' }}>● hot</span>{' '}
        <span style={{ color: '#e67700' }}>● medication</span>{' '}
        <span style={{ color: '#1971c2' }}>● liquid</span>{' '}
        <span style={{ color: '#495057' }}>● electronic</span>
      </p>
    </div>
  )
}

function WhyPanel({ why }) {
  if (!why || why.length === 0) return <p>no findings: nothing fired.</p>
  return (
    <div className="why">
      {why.map((w, i) =>
        typeof w === 'string' ? (
          <p key={i} className="trace-line">{w}</p>
        ) : (
          <div key={i} className="rule">
            <p>
              <b>{w.rule}</b>{' '}
              <span className={w.hard ? 'hard' : 'soft'}>
                {w.hard ? 'hard' : 'soft'}
              </span>{' '}
              <span className="origin">{w.origin}</span>
            </p>
            <p>{w.reason}</p>
            <p>
              predicates:{' '}
              {Object.entries(w.predicates || {})
                .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                .join(', ')}
            </p>
            <p>steps: {(w.steps || []).join(', ') || '—'}</p>
            <p>
              relations:{' '}
              {(w.relations || [])
                .map((r) => `${r.subj} ${r.rel} ${r.obj}`)
                .join('; ') || '—'}
            </p>
          </div>
        ),
      )}
    </div>
  )
}

function VerdictCard({ round, data, open, onToggle }) {
  const v = data.verdict
  const color = KIND_COLORS[v ? v.kind : 'ERROR']
  return (
    <div className="card">
      <p>
        <span className="badge" style={{ background: color }}>
          R{round} {v ? v.kind : 'ERROR'}
        </span>{' '}
        {(v ? v.findings : []).map((f) => f.rule).join(', ')}
        {data.error && <span> {data.error}</span>}
      </p>
      {data.proposal && (
        <p className="dim">
          {data.proposal.model} · {data.proposal.latency_s}s ·{' '}
          {data.proposal.n_steps} steps
        </p>
      )}
      {v && v.feedback && v.feedback.length > 0 && (
        <p className="dim">constraints: {v.feedback.join('; ')}</p>
      )}
      {v && (
        <button onClick={onToggle}>{open ? 'Hide Why?' : 'Why?'}</button>
      )}
      {open && v && <WhyPanel why={v.why_path} />}
    </div>
  )
}

function Timeline({ rounds, halts, clears, done, onRound }) {
  const nums = Object.keys(rounds)
    .map(Number)
    .sort((a, b) => a - b)
  if (nums.length === 0 && halts.length === 0 && !done) {
    return <p>no rounds yet</p>
  }
  return (
    <div className="timeline">
      {nums.map((n, i) => {
        const r = rounds[n]
        const kind = r.verdict ? r.verdict.kind : 'ERROR'
        return (
          <span key={n} className="round" onClick={() => onRound(n)}>
            <span className="node">proposal</span>→
            <span
              className="node"
              style={{ background: KIND_COLORS[kind] }}
            >
              {kind.toLowerCase()}
              {r.verdict && r.verdict.findings.length > 0
                ? ` (${r.verdict.findings.length})`
                : ''}
            </span>
            {r.feedback && <span>→<span className="node">feedback</span></span>}
            {i < nums.length - 1 && <span>→<span className="node">replan</span></span>}
          </span>
        )
      })}
      {halts.map((h, i) => (
        <span key={`h${i}`} className="node" style={{ background: KIND_COLORS.HALT }}>
          HALT {h.dist_cm}cm
        </span>
      ))}
      {clears.map((c, i) => (
        <span key={`c${i}`} className="node clear">
          clear→R{c.resumed_round}
        </span>
      ))}
      {done && (
        <span
          className="node"
          style={{ background: KIND_COLORS[done.status] || '#6e7781' }}
        >
          {done.status}
        </span>
      )}
    </div>
  )
}

export default function App() {
  const [instruction, setInstruction] = useState('give me the knife')
  const [connected, setConnected] = useState(false)
  const [image, setImage] = useState(null)
  const [boxes, setBoxes] = useState([])
  const [status, setStatus] = useState('idle')
  const [graph, setGraph] = useState(null)
  const [rounds, setRounds] = useState({})
  const [halts, setHalts] = useState([])
  const [clears, setClears] = useState([])
  const [done, setDone] = useState(null)
  const [ask, setAsk] = useState(null)
  const [askDecision, setAskDecision] = useState(null)
  const [tab, setTab] = useState('graph')
  const [whyRound, setWhyRound] = useState(null)
  const [running, setRunning] = useState(false)
  const [ownerToken] = useState(
    () => new URLSearchParams(location.search).get('owner') || '',
  )
  const runRef = useRef(null)

  useEffect(() => {
    let ws = null
    let timer = null
    let alive = true
    function resetRun(runId) {
      runRef.current = runId
      setRounds({})
      setHalts([])
      setClears([])
      setDone(null)
      setAsk(null)
      setAskDecision(null)
      setGraph(null)
      setWhyRound(null)
    }
    function mergeRound(n, patch) {
      setRounds((prev) => ({ ...prev, [n]: { ...prev[n], ...patch } }))
    }
    function onMessage(msg) {
      const ev = JSON.parse(msg.data)
      if (ev.run_id === 0 && runRef.current > 0) return // stale idle scene
      if (ev.run_id !== runRef.current) resetRun(ev.run_id)
      if (ev.type === 'frame') {
        setImage(`data:image/jpeg;base64,${ev.image}`)
        setBoxes(ev.boxes || [])
      } else if (ev.type === 'graph') {
        setGraph(ev.graph)
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
        setStatus(`Round ${ev.round}: ${ev.kind}`)
      } else if (ev.type === 'feedback') {
        mergeRound(ev.round, { feedback: ev.note })
      } else if (ev.type === 'path') {
        mergeRound(ev.round, { path: { points: ev.points, fires: ev.fires } })
      } else if (ev.type === 'halt') {
        setHalts((prev) => [
          ...prev,
          { t: ev.t, dist_cm: ev.dist_cm, what: ev.what },
        ])
        setStatus(`HALT t=${ev.t}s: ${ev.what}`)
      } else if (ev.type === 'clear') {
        setClears((prev) => [
          ...prev,
          { t: ev.t, resumed_round: ev.resumed_round },
        ])
        setStatus(`path clear, resumed round ${ev.resumed_round}`)
      } else if (ev.type === 'ask') {
        setAsk(ev)
        setTab('verdicts')
        setStatus(`ASK: ${ev.question}`)
      } else if (ev.type === 'done') {
        setDone({ status: ev.status, detail: ev.detail })
        if (ev.detail && ev.detail.ask) setAskDecision(ev.detail.ask.decision)
        setStatus(`done: ${ev.status}`)
        setRunning(false)
      }
    }
    function connect() {
      if (!alive) return
      ws = new WebSocket(WS_URL)
      ws.onopen = () => {
        setConnected(true)
        fetch('/scene?preset=default').catch(() => {})
      }
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

  async function submit(e) {
    e.preventDefault()
    setStatus('planning…')
    setRunning(true)
    const r = await fetch('/instruction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    })
    if (r.status === 409) {
      setStatus('busy: a run is already in progress')
      setRunning(false)
    } else if (!r.ok) {
      setStatus(`server error ${r.status}`)
      setRunning(false)
    }
  }

  async function setPreset(name) {
    await fetch(`/scene?preset=${name}`).catch(() => {})
  }

  async function decide(decision) {
    const r = await fetch(`/ask/${ask.ask_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, token: ownerToken }),
    })
    if (r.ok) setAskDecision(decision)
    else setStatus(`approval failed: ${r.status}`)
  }

  function openWhy(n) {
    setTab('verdicts')
    setWhyRound(n)
  }

  const roundNums = Object.keys(rounds)
    .map(Number)
    .sort((a, b) => a - b)
  const whyForGraph =
    whyRound !== null && rounds[whyRound] && rounds[whyRound].verdict
      ? rounds[whyRound].verdict.why_path
      : null
  const pathRound =
    whyRound !== null && rounds[whyRound] && rounds[whyRound].path
      ? whyRound
      : [...roundNums].reverse().find((n) => rounds[n].path)
  const shownPath = pathRound !== undefined ? rounds[pathRound].path : null

  return (
    <div className="dash">
      <h1>Sentinel dashboard</h1>
      <form onSubmit={submit} className="row">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="instruction"
          size={48}
        />
        <button type="submit">Run</button>
        <span className={connected ? 'ok' : 'bad'}>
          {connected ? '● ws connected' : '○ ws disconnected'}
        </span>
      </form>
      <p className="status">{status}</p>
      <p className="row presets">
        Scene:
        <button onClick={() => setPreset('default')} disabled={running}>
          Default
        </button>
        <button
          onClick={() => setPreset('cup_next_to_laptop')}
          disabled={running}
        >
          Cup next to laptop
        </button>
      </p>
      <div className="split">
        <div className="left">
          <div className="view">
            {image ? (
              <img src={image} alt="sim camera" />
            ) : (
              <div className="placeholder">
                <p>loading scene...</p>
              </div>
            )}
            {image && (
              <svg viewBox="0 0 640 480" preserveAspectRatio="none">
                {boxes.map((b) => (
                  <g key={b.id}>
                    <rect
                      x={b.x0} y={b.y0}
                      width={b.x1 - b.x0} height={b.y1 - b.y0}
                    />
                    <text x={b.x0 + 3} y={b.y0 + 13}>
                      {b.id} {b.conf != null ? b.conf.toFixed(2) : ''}
                    </text>
                  </g>
                ))}
              </svg>
            )}
          </div>
          <h2>Timeline</h2>
          <Timeline
            rounds={rounds}
            halts={halts}
            clears={clears}
            done={done}
            onRound={openWhy}
          />
        </div>
        <div className="right">
          <div className="tabs">
            <button
              className={tab === 'graph' ? 'active' : ''}
              onClick={() => setTab('graph')}
            >
              Graph
            </button>
            <button
              className={tab === 'verdicts' ? 'active' : ''}
              onClick={() => setTab('verdicts')}
            >
              Verdicts
            </button>
          </div>
          {tab === 'graph' && (
            <GraphTab graph={graph} why={whyForGraph} path={shownPath} />
          )}
          {tab === 'verdicts' && (
            <div>
              {ask && (
                <div className="card ask">
                  <p>
                    <span
                      className="badge"
                      style={{ background: KIND_COLORS.ASK }}
                    >
                      ASK R{ask.round}
                    </span>{' '}
                    {ask.question}
                  </p>
                  <p className="dim">
                    {ask.findings.map((f) => f.rule).join(', ')}
                  </p>
                  {askDecision ? (
                    <p>decision: {askDecision}</p>
                  ) : ownerToken ? (
                    <p>
                      <button onClick={() => decide('approve')}>
                        Approve
                      </button>{' '}
                      <button onClick={() => decide('deny')}>Deny</button>
                    </p>
                  ) : (
                    <p className="dim">
                      owner approval required (open with ?owner=…)
                    </p>
                  )}
                </div>
              )}
              {roundNums.map((n) => (
                <VerdictCard
                  key={n}
                  round={n}
                  data={rounds[n]}
                  open={whyRound === n}
                  onToggle={() => setWhyRound(whyRound === n ? null : n)}
                />
              ))}
              {halts.map((h, i) => (
                <div key={`h${i}`} className="card">
                  <p>
                    <span
                      className="badge"
                      style={{ background: KIND_COLORS.HALT }}
                    >
                      HALT
                    </span>{' '}
                    t={h.t}s · {h.dist_cm} cm · {h.what}
                  </p>
                </div>
              ))}
              {roundNums.length === 0 && halts.length === 0 && !ask && (
                <p>no verdicts yet</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
