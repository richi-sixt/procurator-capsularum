import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { Change, Status } from '../types'
import { ESTIMATE, WINDOW_FROM, visibleRange } from '../windowing'

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
  const windowed = rows.length > WINDOW_FROM
  const wrap = useRef<HTMLDivElement>(null)
  const [heights] = useState(() => new Map<string, number>())
  const [scrollTop, setScrollTop] = useState(0)
  const [viewport, setViewport] = useState(600)
  const [, remeasure] = useState(0)
  const raf = useRef(0)

  const onScroll = useCallback(() => {
    if (raf.current) return
    raf.current = requestAnimationFrame(() => {
      raf.current = 0
      if (wrap.current) setScrollTop(wrap.current.scrollTop)
    })
  }, [])

  useLayoutEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => setViewport(el.clientHeight))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Echte Zeilenhöhen merken. Ändert sich eine, wird neu berechnet.
  useLayoutEffect(() => {
    if (!windowed || !wrap.current) return
    let changed = false
    wrap.current.querySelectorAll<HTMLTableRowElement>('tr[data-key]').forEach((tr) => {
      const key = tr.dataset.key as string
      const h = tr.offsetHeight
      if (Math.abs((heights.get(key) ?? ESTIMATE) - h) > 1) { heights.set(key, h); changed = true }
    })
    if (changed) requestAnimationFrame(() => remeasure((n) => n + 1))
  })

  const range = windowed
    ? visibleRange(rows.map((c) => c.src), heights, scrollTop, viewport)
    : { start: 0, end: rows.length, before: 0, after: 0 }
  const shown = rows.slice(range.start, range.end)
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
    <div className="table-wrap" ref={wrap} onScroll={windowed ? onScroll : undefined}>
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
        {windowed && range.before > 0 && <tr aria-hidden style={{ height: range.before }}><td colSpan={4} style={{ padding: 0, border: 0 }} /></tr>}
        {shown.map((c) => {
          const active = c.status === 'ok'
          return (
            <tr key={c.src} data-key={c.src} className={`row-${c.status}${active && p.disabled.has(c.src) ? ' off' : ''}`}
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
        {windowed && range.after > 0 && <tr aria-hidden style={{ height: range.after }}><td colSpan={4} style={{ padding: 0, border: 0 }} /></tr>}
      </tbody>
    </table>
    </div>
  )
}
