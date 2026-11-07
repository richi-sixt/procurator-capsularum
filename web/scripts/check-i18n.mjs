// Prüft, dass jeder Text, der durch t() oder tx() läuft, eine englische Übersetzung hat und dass die
// Platzhalter ({name}) in beiden Sprachen gleich sind. Aufruf: npm run check:i18n
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = new URL('../src/', import.meta.url).pathname
const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p)
    else if (/\.(ts|tsx)$/.test(name) && !['locale-en.ts', 'i18n.ts'].includes(name)) files.push(p)
  }
}
walk(SRC)

const unescape = (s) => s.replace(/\\(['"`\\])/g, '$1')
const keys = new Set()
const STR = String.raw`'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)"`
for (const file of files) {
  const text = readFileSync(file, 'utf8')
  // t('…') und tx('…')
  for (const m of text.matchAll(new RegExp(String.raw`\bt[x]?\(\s*(?:${STR})`, 'g'))) keys.add(unescape(m[1] ?? m[2]))
  // t(bedingung ? '…' : '…')
  for (const m of text.matchAll(new RegExp(String.raw`\bt\(\s*[^'"\`)]*\?\s*(?:${STR})\s*:\s*(?:${STR})`, 'g'))) {
    keys.add(unescape(m[1] ?? m[2])); keys.add(unescape(m[3] ?? m[4]))
  }
  // Übersetzung zur Laufzeit: t(LABEL[…]) – die Werte der Tabelle zählen mit
  const label = /const LABEL[^=]*=\s*\{([^}]*)\}/.exec(text)
  if (label) for (const m of label[1].matchAll(/:\s*'([^']*)'/g)) keys.add(m[1])
  // t(…) mit Tabelle ist nicht prüfbar, deshalb gilt: nur Zeichenketten oder LABEL
}

const src = readFileSync(join(SRC, 'locale-en.ts'), 'utf8')
const EN = {}
for (const m of src.matchAll(new RegExp(String.raw`^\s*(?:${STR})\s*:\s*(?:\n\s*)?(?:${STR})\s*,?\s*$`, 'gm'))) {
  EN[unescape(m[1] ?? m[2])] = unescape(m[3] ?? m[4])
}

const fields = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
const problems = []
for (const k of keys) if (!(k in EN)) problems.push(`Englisch fehlt: ${k}`)
for (const [de, en] of Object.entries(EN)) {
  if (fields(de) !== fields(en)) problems.push(`Platzhalter weichen ab: ${de}`)
  if (!keys.has(de)) problems.push(`Nicht mehr verwendet: ${de}`)
}
if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`i18n ok: ${keys.size} Texte, alle übersetzt`)
