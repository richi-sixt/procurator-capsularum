import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setApiLang } from '../api'
import { DEFAULT_PREFS, I18nContext, makeT, makeTx, resolveLang, type Prefs } from '../i18n'

const CACHE = 'pc.prefs'

// Zuletzt bekannte Darstellung aus dem Browserspeicher, damit beim Start nichts aufblitzt. Massgebend
// ist der Server (die Desktop-App hat bei jedem Start einen anderen Browserspeicher).
const cached = (): Prefs => {
  try {
    return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(CACHE) ?? '{}') as Partial<Prefs>) }
  } catch { return DEFAULT_PREFS }
}

export default function I18nProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefsState] = useState<Prefs>(cached)
  const lang = resolveLang(prefs.language)
  setApiLang(lang)

  useEffect(() => {
    api.prefs().then((p) => setPrefsState(p)).catch(() => undefined)
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
    if (prefs.theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.dataset.theme = prefs.theme
    try { localStorage.setItem(CACHE, JSON.stringify(prefs)) } catch { /* ohne Speicher geht es auch */ }
  }, [lang, prefs])

  const setPrefs = useCallback((patch: Partial<Prefs>) => {
    setPrefsState((cur) => ({ ...cur, ...patch }))
    void api.savePrefs(patch).then((p) => setPrefsState(p)).catch(() => undefined)
  }, [])

  const value = useMemo(
    () => ({ lang, t: makeT(lang), tx: makeTx(lang), prefs, setPrefs }),
    [lang, prefs, setPrefs],
  )
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
