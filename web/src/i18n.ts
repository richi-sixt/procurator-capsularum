// Zweisprachige Oberfläche: Deutsch ist die Quellsprache, der deutsche Text ist der Schlüssel.
// Fehlt eine englische Übersetzung, erscheint der deutsche Text. `scripts/check-i18n.mjs` prüft das.
import { createContext, createElement, Fragment, useContext, type ReactNode } from 'react'
import { EN } from './locale-en'

export type Lang = 'de' | 'en'
export type LangPref = 'auto' | Lang
export type ThemePref = 'auto' | 'light' | 'dark'
export type Prefs = { language: LangPref; theme: ThemePref; thumbs: boolean }
export type Params = Record<string, string | number>
export type Translate = (key: string, params?: Params) => string
export type TranslateNodes = (key: string, params: Record<string, ReactNode>) => ReactNode[]

export const DEFAULT_PREFS: Prefs = { language: 'auto', theme: 'auto', thumbs: true }

// Sprache des Browsers, wenn nichts gewählt ist: Deutsch bleibt Deutsch, alles andere Englisch.
export const browserLang = (): Lang =>
  (typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('de')) ? 'de' : 'en'

export const resolveLang = (pref: LangPref): Lang => (pref === 'auto' ? browserLang() : pref)

const fill = (text: string, params?: Params): string =>
  params ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : text

export const makeT = (lang: Lang): Translate => (key, params) =>
  fill(lang === 'en' ? (EN[key] ?? key) : key, params)

// Für Texte mit eingebauten Elementen, zum Beispiel «{n} Dateien» mit fettem n.
export const makeTx = (lang: Lang): TranslateNodes => (key, params) => {
  const text = lang === 'en' ? (EN[key] ?? key) : key
  return text.split(/(\{\w+\})/).map((part, i) => {
    const name = /^\{(\w+)\}$/.exec(part)?.[1]
    return name && name in params ? createElement(Fragment, { key: i }, params[name]) : part
  })
}

export type I18n = {
  lang: Lang
  t: Translate
  tx: TranslateNodes
  prefs: Prefs
  setPrefs: (patch: Partial<Prefs>) => void
}

export const I18nContext = createContext<I18n>({
  lang: 'de', t: makeT('de'), tx: makeTx('de'), prefs: DEFAULT_PREFS, setPrefs: () => undefined,
})

export const useI18n = (): I18n => useContext(I18nContext)
export const useT = (): Translate => useContext(I18nContext).t
