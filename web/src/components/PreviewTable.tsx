import { useState } from 'react'
import type { Change, Status } from '../types'

type Props = {
  changes: Change[]
  showFolder: boolean
  showSkipped: boolean
  listing?: boolean // nur Dateiliste: keine Checkboxen, keine Statusspalte
  disabled: Set<string>
  onToggle: (src: string) => void
  onToggleAll: (enable: boolean) => void
  draggable: boolean
  onReorder: (srcs: string[]) => void
  onEdit?: (src: string, text: string) => Promise<void> // Ziel von Hand ändern (KI-Vorschläge)
}

const LABEL: Record<Status, string> = { ok: 'Bereit', skip: 'Übersprungen', conflict: 'Konflikt', error: 'Fehler' }

export default function PreviewTable(p: Props) {
  const [dragging, setDragging] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const rows = p.showSkipped ? p.changes : p.changes.filter((c) => c.status !== 'skip')
  const okRows = p.changes.filter((c) => c.status === 'ok')
  const allOn = okRows.length > 0 && okRows.every((c) => !p.disabled.has(c.src))

  const drop = (target: string) => {
    if (!dragging || dragging === target) return
    const srcs = p.changes.map((c) => c.src).filter((s) => s !== dragging)
    srcs.splice(srcs.indexOf(target), 0, dragging)
    p.onReorder(srcs)
    setDragging(null)
  }

  const startEdit = (c: Change) => { setEditing(c.src); setDraft(c.editable ?? '') }
  const saveEdit = async (c: Change) => {
    const text = draft.trim()
    setEditing(null)
    if (text && text !== c.editable && p.onEdit) await p.onEdit(c.src, text)
  }

  return (
    <table className="preview">
      <thead>
        <tr>
          <th className="narrow">
            {!p.listing && <input type="checkbox" aria-label="Alle auswählen" checked={allOn}
              disabled={okRows.length === 0} onChange={(e) => p.onToggleAll(e.target.checked)} />}
          </th>
          <th>Original</th>
          <th>{p.listing ? '' : 'Neu'}</th>
          <th>{p.listing ? '' : 'Status'}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const active = c.status === 'ok'
          return (
            <tr key={c.src} className={`row-${c.status}${active && p.disabled.has(c.src) ? ' off' : ''}`}
              title={c.reason || undefined}
              draggable={p.draggable} onDragStart={() => setDragging(c.src)}
              onDragOver={(e) => p.draggable && e.preventDefault()} onDrop={() => drop(c.src)}>
              <td className="narrow">
                {active
                  ? <input type="checkbox" aria-label={`${c.srcName} umbenennen`} checked={!p.disabled.has(c.src)}
                      onChange={() => p.onToggle(c.src)} />
                  : null}
              </td>
              <td>
                {p.draggable && <span className="grip" aria-hidden>⋮⋮ </span>}
                {c.srcName}
                {c.sensitive && <span className="badge sensitive" title={`Sensibel (Treffer: ${c.sensitive}). Wird nie an ein KI-Modell gesendet.`}>🔒 sensibel</span>}
                {p.showFolder && <div className="muted small">{c.folder}</div>}
              </td>
              <td className="new">
                {editing === c.src ? (
                  <input autoFocus className="edit" value={draft} spellCheck={false}
                    aria-label={`Ziel für ${c.srcName}`}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') void saveEdit(c); if (e.key === 'Escape') setEditing(null) }}
                    onBlur={() => void saveEdit(c)} />
                ) : (
                  <>
                    {p.listing ? '' : (c.dstName ?? '–')}
                    {!p.listing && c.dstFolder && <div className="muted small">{c.dstFolder}</div>}
                    {!p.listing && p.onEdit && c.editable != null && (
                      <button className="link edit-btn" aria-label={`Ziel für ${c.srcName} ändern`}
                        title="Ziel ändern (Ordner/Name)" onClick={() => startEdit(c)}>✎</button>
                    )}
                  </>
                )}
              </td>
              <td>{!p.listing && <span className={`badge ${c.status}`}>{LABEL[c.status]}</span>}
                {c.reason && <div className="muted small">{c.reason}</div>}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
