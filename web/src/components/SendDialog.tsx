import type { SendPreview } from '../types'
import { useI18n } from '../i18n'

type Props = { info: SendPreview; onConfirm: () => void; onCancel: () => void }

// Bestätigung vor dem Senden an einen Cloud-Anbieter: zeigt, was den Rechner verlassen würde.
export default function SendDialog({ info, onConfirm, onCancel }: Props) {
  const { t, tx } = useI18n()
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog wide" role="dialog" aria-label={t('Daten senden?')} onClick={(e) => e.stopPropagation()}>
        <h2>{t('Daten an die Cloud senden?')}</h2>
        <p>
          {tx('Diese Angaben gehen an {provider}{model} und verlassen deinen Rechner.', {
            provider: <strong>{info.provider === 'claude' ? 'Anthropic (Claude)' : info.provider}</strong>,
            model: info.model ? ` (${t('Modell {name}', { name: info.model })})` : '',
          })}
        </p>
        <ul>
          <li>{tx('{files} Dateien in {batches} Paketen werden gesendet.', { files: <strong>{info.files}</strong>, batches: info.batches ?? 0 })}</li>
          <li>{tx('{n} sensible Dateien bleiben zurück, auch ihre Namen.', { n: <strong>{info.withheld}</strong> })}</li>
          <li>{t('{n} Dateien sind schon bekannt und werden nicht erneut gesendet.', { n: info.cached ?? 0 })}</li>
          <li>{t('Datenschutzstufe {n}', { n: info.privacyLevel ?? 0 })}: {info.privacyText}.</li>
          {info.learning && info.learning.text && (
            <li>
              {t('Aus deinen früheren Entscheidungen gehen zusätzlich {examples} Beispiele, {habits} Gewohnheiten und {rejected} abgelehnte Vorschläge mit (sensible Dateien nie).', info.learning)}
            </li>
          )}
        </ul>
        {info.sample && info.sample.length > 0 && (
          <>
            <h3>{t('So sehen die ersten Einträge aus')}</h3>
            <pre className="sample">{info.sample.map((r) => JSON.stringify(r)).join('\n')}</pre>
          </>
        )}
        {info.learning && info.learning.text && (
          <>
            <h3>{t('Frühere Entscheidungen, die mitgehen')}</h3>
            <pre className="sample">{info.learning.text}</pre>
          </>
        )}
        <div className="dialog-actions">
          <button onClick={onCancel}>{t('Abbrechen')}</button>
          <button className="primary" onClick={onConfirm}>{t('Ja, senden')}</button>
        </div>
      </div>
    </div>
  )
}
