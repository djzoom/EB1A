import zhCN from './locales/zh-CN.js'
import hi from './locales/hi.js'
import es from './locales/es.js'
import ptBR from './locales/pt-BR.js'
import ja from './locales/ja.js'
import ko from './locales/ko.js'
import de from './locales/de.js'
import fr from './locales/fr.js'
import ar from './locales/ar.js'
import it from './locales/it.js'

// 词典随 ui.js 静态打包；新增语言必须先通过完整性校验，再加入 catalogs。
export const catalogs = { 'zh-CN': zhCN, hi, es, 'pt-BR': ptBR, ja, ko, ar, de, fr, it }
export const languages = [
  { id: 'zh-CN', name: '中文', locale: 'zh-CN' },
  { id: 'hi', name: 'हिन्दी', locale: 'hi-IN' },
  { id: 'es', name: 'Español', locale: 'es' },
  { id: 'pt-BR', name: 'Português', locale: 'pt-BR' },
  { id: 'ja', name: '日本語', locale: 'ja-JP' },
  { id: 'ko', name: '한국어', locale: 'ko-KR' },
  { id: 'ar', name: 'العربية', locale: 'ar' },
  { id: 'de', name: 'Deutsch', locale: 'de-DE' },
  { id: 'fr', name: 'Français', locale: 'fr-FR' },
  { id: 'it', name: 'Italiano', locale: 'it-IT' }
]

const storageKey = 'gc_language'
const listeners = new Set()
const formatters = new Map()
const owns = (object, key) => Object.prototype.hasOwnProperty.call(object, key)
const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined'
let currentLocale = 'zh-CN'

function placeholders(message) {
  return [...new Set([...message.matchAll(/\{([A-Za-z][A-Za-z0-9]*)\}/g)].map(match => match[1]))].sort().join(',')
}

export function validateCatalog(catalog) {
  const errors = []
  for (const [key, original] of Object.entries(zhCN)) {
    if (typeof catalog?.[key] !== 'string' || !catalog[key].trim()) errors.push(`Missing message: ${key}`)
    else if (placeholders(original) !== placeholders(catalog[key])) errors.push(`Placeholder mismatch: ${key}`)
  }
  for (const key of Object.keys(catalog || {})) if (!owns(zhCN, key)) errors.push(`Unknown message: ${key}`)
  return errors
}

export function availableLanguages() {
  return languages.filter(language => owns(catalogs, language.id) && !validateCatalog(catalogs[language.id]).length)
}

function normalizeLocale(value) {
  if (typeof value !== 'string') return null
  const normalized = value.toLowerCase().replace('_', '-')
  const language = languages.find(item => item.id.toLowerCase() === normalized || item.id.toLowerCase().split('-')[0] === normalized.split('-')[0])
  return language && owns(catalogs, language.id) && !validateCatalog(catalogs[language.id]).length ? language.id : null
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character])
}

function interpolate(key, parameters, escape) {
  const message = catalogs[currentLocale]?.[key] ?? zhCN[key]
  if (typeof message !== 'string') throw new Error(`Unknown i18n message: ${key}`)
  return message.replace(/\{([A-Za-z][A-Za-z0-9]*)\}/g, (_, name) => {
    if (!owns(parameters, name)) throw new Error(`Missing i18n parameter: ${key}.${name}`)
    return escape ? escapeHtml(parameters[name]) : String(parameters[name] ?? '')
  })
}

// t 保留经过审核的词典富文本，但一律转义插值。text 仅用于 React/textContent/属性。
export function t(key, parameters = {}) { return interpolate(key, parameters, true) }
export function text(key, parameters = {}) { return interpolate(key, parameters, false) }
export function getLocale() { return currentLocale }
export function subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener) }

function formatter(type, options) {
  const locale = languages.find(language => language.id === currentLocale).locale
  const key = JSON.stringify([type, locale, options])
  if (!formatters.has(key)) formatters.set(key, new Intl[type](locale, options))
  return formatters.get(key)
}

export function formatNumber(value, options = {}) {
  return formatter('NumberFormat', options).format(value)
}

export function formatDate(value, options = {}) {
  return formatter('DateTimeFormat', { calendar: 'gregory', year: 'numeric', month: 'long', ...options }).format(value)
}

export function formatMonth(year, month) {
  return formatDate(Date.UTC(year, month - 1, 1), { timeZone: 'UTC' })
}

export function formatUnit(value, unit, options = {}) {
  return formatNumber(value, { style: 'unit', unit, unitDisplay: 'long', maximumFractionDigits: 1, ...options })
}

export function formatDuration(months) {
  const total = Math.max(0, Math.round(months))
  const years = Math.floor(total / 12)
  const remainder = total % 12
  const parts = []
  if (years) parts.push(formatUnit(years, 'year', { maximumFractionDigits: 0 }))
  if (remainder || !years) parts.push(formatUnit(remainder, 'month', { maximumFractionDigits: 0 }))
  return formatter('ListFormat', { style: 'long', type: 'unit' }).format(parts)
}

export function formatRelative(value, unit) {
  return formatter('RelativeTimeFormat', { numeric: 'always' }).format(value, unit)
}

export function normalizeDigits(value) {
  return String(value).replace(/[٠-٩۰-۹०-९]/g, digit => {
    const code = digit.charCodeAt(0)
    return String(code - (code >= 0x0966 ? 0x0966 : code >= 0x06f0 ? 0x06f0 : 0x0660))
  })
}

// 只处理显式标记；不会扫描/猜译文本，不会观察或重写 React、图表的动态 DOM。
export function applyStatic(root = document) {
  const selector = '[data-i18n], [data-i18n-html], [data-i18n-title], [data-i18n-aria-label], [data-i18n-placeholder], [data-i18n-content]'
  const nodes = [...root.querySelectorAll(selector)]
  if (root.matches?.(selector)) nodes.unshift(root)
  for (const element of nodes) {
    const parameters = element.dataset.i18nParams ? JSON.parse(element.dataset.i18nParams) : {}
    if (element.dataset.i18n) element.textContent = text(element.dataset.i18n, parameters)
    if (element.dataset.i18nHtml) element.innerHTML = t(element.dataset.i18nHtml, parameters)
    for (const attribute of ['title', 'aria-label', 'placeholder', 'content']) {
      const key = element.getAttribute(`data-i18n-${attribute}`)
      if (key) element.setAttribute(attribute, text(key, parameters))
    }
  }
}

export function setLocale(value, { persist = true, notify = true } = {}) {
  const next = normalizeLocale(value)
  if (!next) return false
  const changed = next !== currentLocale
  currentLocale = next
  if (isBrowser) {
    document.documentElement.lang = currentLocale
    document.documentElement.dir = currentLocale === 'ar' ? 'rtl' : 'ltr'
    if (persist) {
      try { localStorage.setItem(storageKey, currentLocale) } catch {}
      // 手动选择优先于当前分享片段的语言；只更新片段，不把个人条件送入 URL 查询。
      try {
        const hash = new URLSearchParams(window.location.hash.slice(1))
        if (hash.has('lang')) {
          hash.set('lang', currentLocale)
          window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search + '#' + hash)
        }
      } catch {}
    }
    applyStatic()
  }
  if (changed && notify) {
    listeners.forEach(listener => listener())
    if (isBrowser) window.dispatchEvent(new CustomEvent('gc:localechange', { detail: { locale: currentLocale } }))
  }
  return true
}

if (isBrowser) {
  let selected = null
  try { selected = normalizeLocale(new URLSearchParams(window.location.hash.slice(1)).get('lang')) } catch {}
  if (!selected) {
    try { selected = normalizeLocale(localStorage.getItem(storageKey)) } catch {}
  }
  setLocale(selected || 'zh-CN', { persist: false, notify: false })
  window.GCI18n = {
    t, text, getLocale, setLocale, subscribe, availableLanguages, normalizeLocale,
    formatNumber, formatDate, formatMonth, formatUnit, formatDuration, formatRelative,
    normalizeDigits, escapeHtml, applyStatic, storageKey, validateCatalog
  }
}
