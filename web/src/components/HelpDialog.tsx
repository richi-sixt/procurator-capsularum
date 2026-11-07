import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { HelpContent, HelpPage } from '../types'

type Props = { onClose: () => void; start?: string }

// Die Hilfe zeigt die Seiten aus docs/ (vom lokalen Server als HTML geliefert, rohes HTML ist dort
// schon ausgeschlossen). Verweise auf andere Seiten und Anker bleiben im Dialog.
export default function HelpDialog({ onClose, start }: Props) {
  const [pages, setPages] = useState<HelpPage[]>([])
  const [page, setPage] = useState<HelpContent | null>(null)
  const [error, setError] = useState('')
  const body = useRef<HTMLDivElement>(null)
  const pending = useRef<string | null>(null)

  const open = useCallback((name: string, anchor?: string) => {
    pending.current = anchor ?? null
    setError('')
    api.helpPage(name).then(setPage).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api.helpPages().then((list) => {
      setPages(list)
      const first = start && list.some((p) => p.name === start) ? start : list[0]?.name
      if (first) open(first)
    }).catch((e: Error) => setError(e.message))
  }, [open, start])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const scrollTo = (id: string) => {
    const el = body.current?.querySelector(`[id="${CSS.escape(id)}"]`)
    if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  // Nach dem Laden einer Seite: an den gewünschten Anker springen, sonst nach oben
  useEffect(() => {
    if (!page) return
    if (pending.current) scrollTo(pending.current)
    else body.current?.scrollTo({ top: 0 })
    pending.current = null
  }, [page])

  const onClick = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a')
    if (!a) return
    const target = a.getAttribute('data-help')
    const href = a.getAttribute('href') ?? ''
    if (target) {
      e.preventDefault()
      const anchor = a.getAttribute('data-anchor') ?? undefined
      if (page && target === page.name) { if (anchor) scrollTo(anchor) } else open(target, anchor)
    } else if (href.startsWith('#')) {
      e.preventDefault()
      if (href.length > 1) scrollTo(decodeURIComponent(href.slice(1)))
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog help" role="dialog" aria-label="Hilfe" onClick={(e) => e.stopPropagation()}>
        <nav className="help-nav" aria-label="Hilfeseiten">
          <h2>Hilfe</h2>
          {pages.map((p) => (
            <div key={p.name}>
              <button className={`link help-page${page?.name === p.name ? ' current' : ''}`}
                onClick={() => open(p.name)}>{p.title}</button>
              {page?.name === p.name && (
                <ul className="help-toc">
                  {page.toc.filter((t) => t.level === 2).map((t) => (
                    <li key={t.id}><button className="link" onClick={() => scrollTo(t.id)}>{t.text}</button></li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </nav>
        <div className="help-body" ref={body} onClick={onClick}>
          {error && <p className="error" role="alert">{error}</p>}
          {!page && !error && <p className="muted">Lädt …</p>}
          {page && <article className="markdown" dangerouslySetInnerHTML={{ __html: page.html }} />}
        </div>
        <button className="help-close" onClick={onClose} aria-label="Hilfe schliessen">Schliessen</button>
      </div>
    </div>
  )
}
