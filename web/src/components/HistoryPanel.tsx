import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Batch } from '../types'

type Props = { onClose: () => void; onChanged: () => void }

export default function HistoryPanel({ onClose, onChanged }: Props) {
  const [batches, setBatches] = useState<Batch[]>([])
  const [open, setOpen] = useState<number | null>(null)
  const [detail, setDetail] = useState<{ src: string; dst: string }[]>([])
  const [msg, setMsg] = useState('')

  const load = useCallback(() => { void api.history().then(setBatches) }, [])
  useEffect(load, [load])

  const toggle = async (id: number) => {
    if (open === id) { setOpen(null); return }
    setDetail(await api.historyDetail(id))
    setOpen(id)
  }

  const undo = async (b: Batch) => {
    if (b.kind === 'convert' && !window.confirm(
      `Lauf #${b.id}: Die ${b.count} erzeugten Dateien werden gelöscht. Die Originale bleiben unverändert. Fortfahren?`)) return
    const id = b.id
    const r = await api.undo(id)
    setMsg(r.errors.length ? `${r.restored} zurückgesetzt, Fehler: ${r.errors.join('; ')}` : `${r.restored} Dateien ${b.kind === 'convert' ? 'gelöscht' : 'zurückbenannt'}.`)
    load()
    onChanged()
  }

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="dialog wide" role="dialog" aria-label="Verlauf" onClick={(e) => e.stopPropagation()}>
        <h2>Verlauf</h2>
        {msg && <p role="status">{msg}</p>}
        {batches.length === 0 && <p className="muted">Noch keine Läufe.</p>}
        <ul className="history">
          {batches.map((b) => (
            <li key={b.id}>
              <div className="history-row">
                <button className="link" onClick={() => void toggle(b.id)}>
                  #{b.id} · {b.operation} · {b.count} Dateien
                </button>
                <span className="muted small">{b.ts.replace('T', ' ')}</span>
                {b.undone
                  ? <span className="badge skip">Rückgängig</span>
                  : <button onClick={() => void undo(b)}>{b.kind === 'convert' ? 'Erzeugte Dateien löschen' : 'Rückgängig machen'}</button>}
              </div>
              {open === b.id && (
                <ul className="detail">
                  {detail.map((d) => <li key={d.src + d.dst}>{d.src} → {d.dst}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ul>
        <div className="dialog-actions"><button onClick={onClose}>Schliessen</button></div>
      </aside>
    </div>
  )
}
