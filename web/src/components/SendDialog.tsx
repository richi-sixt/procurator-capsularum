import type { SendPreview } from '../types'

type Props = { info: SendPreview; onConfirm: () => void; onCancel: () => void }

// Bestätigung vor dem Senden an einen Cloud-Anbieter: zeigt, was den Rechner verlassen würde.
export default function SendDialog({ info, onConfirm, onCancel }: Props) {
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog wide" role="dialog" aria-label="Daten senden?" onClick={(e) => e.stopPropagation()}>
        <h2>Daten an die Cloud senden?</h2>
        <p>
          Diese Angaben gehen an <strong>{info.provider === 'claude' ? 'Anthropic (Claude)' : info.provider}</strong>
          {info.model ? ` (Modell ${info.model})` : ''} und verlassen deinen Rechner.
        </p>
        <ul>
          <li><strong>{info.files}</strong> Dateien in {info.batches} Paketen werden gesendet.</li>
          <li><strong>{info.withheld}</strong> sensible Dateien bleiben zurück, auch ihre Namen.</li>
          <li>{info.cached} Dateien sind schon bekannt und werden nicht erneut gesendet.</li>
          <li>Datenschutzstufe {info.privacyLevel}: {info.privacyText}.</li>
          {info.learning && info.learning.text && (
            <li>
              Aus deinen früheren Entscheidungen gehen zusätzlich {info.learning.examples} Beispiele,{' '}
              {info.learning.habits} Gewohnheiten und {info.learning.rejected} abgelehnte Vorschläge mit
              (sensible Dateien nie).
            </li>
          )}
        </ul>
        {info.sample && info.sample.length > 0 && (
          <>
            <h3>So sehen die ersten Einträge aus</h3>
            <pre className="sample">{info.sample.map((r) => JSON.stringify(r)).join('\n')}</pre>
          </>
        )}
        {info.learning && info.learning.text && (
          <>
            <h3>Frühere Entscheidungen, die mitgehen</h3>
            <pre className="sample">{info.learning.text}</pre>
          </>
        )}
        <div className="dialog-actions">
          <button onClick={onCancel}>Abbrechen</button>
          <button className="primary" onClick={onConfirm}>Ja, senden</button>
        </div>
      </div>
    </div>
  )
}
