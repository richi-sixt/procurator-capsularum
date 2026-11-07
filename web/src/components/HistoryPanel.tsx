import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Batch } from '../types'
import { useT } from '../i18n'

type Props = { onClose: () => void; onChanged: () => void }

export default function HistoryPanel({ onClose, onChanged }: Props) {
  const t = useT()
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
      t('Lauf #{id}: Die {n} erzeugten Dateien werden gelöscht. Die Originale bleiben unverändert. Fortfahren?', { id: b.id, n: b.count }))) return
    const id = b.id
    const r = await api.undo(id)
    setMsg(r.errors.length ? t('{n} zurückgesetzt, Fehler: {errors}', { n: r.restored, errors: r.errors.join('; ') }) : (b.kind === 'convert' ? t('{n} Dateien gelöscht.', { n: r.restored }) : t('{n} Dateien zurückbenannt.', { n: r.restored })))
    load()
    onChanged()
  }

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="dialog wide" role="dialog" aria-label={t('Verlauf')} onClick={(e) => e.stopPropagation()}>
        <h2>{t('Verlauf')}</h2>
        {msg && <p role="status">{msg}</p>}
        {batches.length === 0 && <p className="muted">{t('Noch keine Läufe.')}</p>}
        <ul className="history">
          {batches.map((b) => (
            <li key={b.id}>
              <div className="history-row">
                <button className="link" onClick={() => void toggle(b.id)}>
                  #{b.id} · {b.operation} · {t('{n} Dateien', { n: b.count })}
                </button>
                <span className="muted small">{b.ts.replace('T', ' ')}</span>
                {b.undone
                  ? <span className="badge skip">{t('Rückgängig')}</span>
                  : <button onClick={() => void undo(b)}>{b.kind === 'convert' ? t('Erzeugte Dateien löschen') : t('Rückgängig machen')}</button>}
              </div>
              {open === b.id && (
                <ul className="detail">
                  {detail.map((d) => <li key={d.src + d.dst}>{d.src} → {d.dst}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ul>
        <div className="dialog-actions"><button onClick={onClose}>{t('Schliessen')}</button></div>
      </aside>
    </div>
  )
}
