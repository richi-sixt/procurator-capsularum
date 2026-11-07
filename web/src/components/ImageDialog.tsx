import { useEffect } from 'react'
import { api } from '../api'
import { thumbUrl } from '../thumbs'
import { useT } from '../i18n'

export type Shot = { src: string; name: string }
type Props = { items: Shot[]; index: number; onIndex: (i: number) => void; onClose: () => void }

// Grosse Ansicht eines Bildes (vom lokalen Server verkleinert, nie das Original).
// Mit den Pfeiltasten (oder den Knöpfen) lässt sich durch alle Bilder der Liste blättern.
export default function ImageDialog({ items, index, onIndex, onClose }: Props) {
  const t = useT()
  const cur = items[index]
  const go = (i: number) => { if (i >= 0 && i < items.length) onIndex(i) }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') { e.preventDefault(); go(index - 1) }
      else if (e.key === 'ArrowRight') { e.preventDefault(); go(index + 1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  if (!cur) return null
  const next = items[index + 1]
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog image-dialog" role="dialog" aria-label={t('Vorschau {name}', { name: cur.name })} onClick={(e) => e.stopPropagation()}>
        <div className="image-stage">
          <button className="nav" aria-label={t('Vorheriges Bild')} disabled={index === 0} onClick={() => go(index - 1)}>‹</button>
          <img key={cur.src} src={thumbUrl(cur.src, 1000)} alt={cur.name} />
          <button className="nav" aria-label={t('Nächstes Bild')} disabled={index >= items.length - 1} onClick={() => go(index + 1)}>›</button>
        </div>
        {next && <img className="preload" src={thumbUrl(next.src, 1000)} alt="" aria-hidden />}
        <div className="dialog-actions">
          <span className="muted">{cur.name} · {index + 1} / {items.length}</span>
          <button onClick={() => void api.reveal(cur.src).catch(() => undefined)}>{t('Im Dateimanager zeigen')}</button>
          <button onClick={onClose}>{t('Schliessen')}</button>
        </div>
      </div>
    </div>
  )
}
