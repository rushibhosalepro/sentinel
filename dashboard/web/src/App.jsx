import { useEffect, useState } from 'react'
import './App.css'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`

export default function App() {
  const [instruction, setInstruction] = useState('give me the knife')
  const [connected, setConnected] = useState(false)
  const [image, setImage] = useState(null)
  const [boxes, setBoxes] = useState([])
  const [status, setStatus] = useState('idle')

  useEffect(() => {
    let ws = null
    let timer = null
    let alive = true
    function onMessage(msg) {
      const ev = JSON.parse(msg.data)
      if (ev.type === 'frame') {
        setImage(`data:image/jpeg;base64,${ev.image}`)
        setBoxes(ev.boxes || [])
      } else if (ev.type === 'verdict') {
        setStatus(`Round ${ev.round}: ${ev.kind}`)
      } else if (ev.type === 'halt') {
        setStatus(`HALT t=${ev.t}s: ${ev.what}`)
      } else if (ev.type === 'clear') {
        setStatus(`path clear, resumed round ${ev.resumed_round}`)
      } else if (ev.type === 'done') {
        setStatus(`done: ${ev.status}`)
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

  async function submit(e) {
    e.preventDefault()
    setStatus('planning…')
    const r = await fetch('/instruction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    })
    if (r.status === 409) setStatus('busy: a run is already in progress')
    else if (!r.ok) setStatus(`server error ${r.status}`)
  }

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
      <div className="view">
        {image ? <img src={image} alt="sim camera" /> : <p>no frame yet</p>}
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
    </div>
  )
}
