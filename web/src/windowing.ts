// Virtuelle Liste: nur die sichtbaren Zeilen zeichnen.

// Ab dieser Zeilenzahl werden nur noch die sichtbaren Zeilen gezeichnet (sonst wird die Seite bei
// Zehntausenden Dateien träge). Darunter bleibt alles wie gehabt.
export const WINDOW_FROM = 200
export const ESTIMATE = 46 // geschätzte Zeilenhöhe in Pixeln, bis die echte gemessen ist
const OVERSCAN = 10 // Zeilen ausserhalb des Bildes, damit Scrollen nicht flackert
const HEAD = 36 // Höhe der Kopfzeile

// Berechnet, welche Zeilen sichtbar sind. Die Höhen sind verschieden (Zeilen mit Grund oder Ordner
// sind höher), deshalb werden sie gemessen und gemerkt.
export function visibleRange(
  keys: string[], heights: Map<string, number>, scrollTop: number, viewport: number,
): { start: number; end: number; before: number; after: number } {
  const n = keys.length
  const top = Math.max(0, scrollTop - HEAD)
  let offset = 0
  let start = 0
  while (start < n) {
    const h = heights.get(keys[start]) ?? ESTIMATE
    if (offset + h > top) break
    offset += h
    start++
  }
  const first = Math.max(0, start - OVERSCAN)
  let before = offset
  for (let i = start - 1; i >= first; i--) before -= heights.get(keys[i]) ?? ESTIMATE
  let end = start
  let seen = offset
  while (end < n && seen < top + viewport) seen += heights.get(keys[end++]) ?? ESTIMATE
  end = Math.min(n, end + OVERSCAN)
  let after = 0
  for (let i = end; i < n; i++) after += heights.get(keys[i]) ?? ESTIMATE
  return { start: first, end, before, after }
}
