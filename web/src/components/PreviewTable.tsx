import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { Change, Status } from '../types'
import { ESTIMATE, WINDOW_FROM, visibleRange } from '../windowing'
import { isPreviewable, thumbUrl } from '../thumbs'
import { api } from '../api'
import ImageDialog from './ImageDialog'
import { useT } from '../i18n'

type Props = {
  changes: Change[]
  showFolder: boolean
  showSkipped: boolean
  thumbs?: boolean // Vorschaubilder bei Bilddateien zeigen
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
  const t = useT()
  const [dragging, setDragging] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [broken] = useState(() => new Set<string>()) // Bilder, die der Server nicht lesen konnte
  const [big, setBig] = useState<string | null>(null) // Pfad des grossen Bildes
  const [revealError, setRevealError] = useState('')
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
  const imageRows = rows.filter((c) => p.thumbs && !c.sensitive && isPreviewable(c.srcName) && !broken.has(c.src))
  const bigIndex = big ? imageRows.findIndex((c) => c.src === big) : -1
  const reveal = (path: string) => {
    setRevealError('')
    api.reveal(path).catch((e: Error) => setRevealError(e.message))
  }
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
            {!p.listing && <input type="checkbox" aria-label={t('Alle auswählen')} checked={allOn}
              disabled={okRows.length === 0} onChange={(e) => p.onToggleAll(e.target.checked)} />}
          </th>
          <th>{t('Original')}</th>
          <th>{p.listing ? '' : t('Neu')}</th>
          <th>{p.listing ? '' : t('Status')}</th>
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
                  ? <input type="checkbox" aria-label={t('{name} umbenennen', { name: c.srcName })} checked={!p.disabled.has(c.src)}
                      onChange={() => p.onToggle(c.src)} />
                  : null}
              </td>
              <td>
                {p.draggable && <span className="grip" aria-hidden>⋮⋮ </span>}
                {p.thumbs && !c.sensitive && isPreviewable(c.srcName) && !broken.has(c.src) && (
                  <button className="thumb-btn" aria-label={t('Vorschau {name}', { name: c.srcName })} title={t('Grösser ansehen')}
                    onClick={() => setBig(c.src)}>
                    <img className="thumb" src={thumbUrl(c.src)} alt="" loading="lazy" width={44} height={44}
                      onError={() => { broken.add(c.src); remeasure((n) => n + 1) }} />
                  </button>
                )}
                {c.srcName}
                <button className="link reveal-btn" aria-label={t('{name} im Dateimanager zeigen', { name: c.srcName })}
                  title={t('Im Dateimanager zeigen')} onClick={() => reveal(c.src)}>📂</button>
                {c.sensitive && <span className="badge sensitive" title={t('Sensibel (Treffer: {hit}). Wird nie an ein KI-Modell gesendet.', { hit: c.sensitive })}>🔒 {t('sensibel')}</span>}
                {p.showFolder && <div className="muted small">{c.folder}</div>}
                {c.related && c.related.length > 0 && (
                  <details className="related" onToggle={() => remeasure((n) => n + 1)}>
                    <summary>{t('Gleiche Dateien')} ({c.relatedTotal ?? c.related.length})</summary>
                    <ul>
                      {c.related.map((r, i) => (
                        <li key={r}>
                          <button className="link reveal-btn" aria-label={t('{name} im Dateimanager zeigen', { name: r })}
                            title={t('Im Dateimanager zeigen')} onClick={() => reveal(r)}>📂</button>
                          <span className="muted small">{r}</span>
                          {i === 0 && c.status === 'ok' && <span className="badge ok">{t('behalten')}</span>}
                        </li>
                      ))}
                      {(c.relatedTotal ?? 0) > c.related.length && (
                        <li className="muted small">{t('und {n} weitere', { n: (c.relatedTotal ?? 0) - c.related.length })}</li>
                      )}
                    </ul>
                  </details>
                )}
              </td>
              <td className="new">
                {editing === c.src ? (
                  <input autoFocus className="edit" value={draft} spellCheck={false}
                    aria-label={t('Ziel für {name}', { name: c.srcName })}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') void saveEdit(c); if (e.key === 'Escape') setEditing(null) }}
                    onBlur={() => void saveEdit(c)} />
                ) : (
                  <>
                    {p.listing ? '' : (c.dstName ?? '–')}
                    {!p.listing && c.dstFolder && <div className="muted small">{c.dstFolder}</div>}
                    {!p.listing && p.onEdit && c.editable != null && (
                      <button className="link edit-btn" aria-label={t('Ziel für {name} ändern', { name: c.srcName })}
                        title={t('Ziel ändern (Ordner/Name)')} onClick={() => startEdit(c)}>✎</button>
                    )}
                  </>
                )}
              </td>
              <td>{!p.listing && <span className={`badge ${c.status}`}>{t(LABEL[c.status])}</span>}
                {c.reason && <div className="muted small">{c.reason}</div>}</td>
            </tr>
          )
        })}
        {windowed && range.after > 0 && <tr aria-hidden style={{ height: range.after }}><td colSpan={4} style={{ padding: 0, border: 0 }} /></tr>}
      </tbody>
    </table>
    {revealError && <p className="error" role="alert">{revealError}</p>}
    {big && bigIndex >= 0 && (
      <ImageDialog items={imageRows.map((c) => ({ src: c.src, name: c.srcName }))} index={bigIndex}
        onIndex={(i) => setBig(imageRows[i].src)} onClose={() => setBig(null)} />
    )}
    </div>
  )
}
