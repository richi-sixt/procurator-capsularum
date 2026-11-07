import { useEffect, type ReactNode } from 'react'
import { useT } from '../i18n'

type Props = { title: string; children: ReactNode; confirmLabel: string; onConfirm: () => void; onCancel: () => void }

// Rückfrage vor einer Aktion, die sich nicht rückgängig machen lässt. Eigener Dialog statt window.confirm,
// weil der in einem Webview (Desktop-App) nicht überall erscheint. Abbrechen ist vorgewählt.
export default function ConfirmDialog({ title, children, confirmLabel, onConfirm, onCancel }: Props) {
  const t = useT()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog" role="alertdialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
        <div className="dialog-actions">
          <button autoFocus onClick={onCancel}>{t('Abbrechen')}</button>
          <button className="danger" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
