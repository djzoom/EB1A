import React, { useCallback, useState, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { createPortal, flushSync } from 'react-dom'
import { Widget } from '@heroui-pro/react/widget'
import { Button } from '@heroui/react/button'
import './share.js'
import { availableLanguages, getLocale, setLocale, subscribe, text } from './i18n.js'

function LanguageSelect({ id }) {
  const locale = useSyncExternalStore(subscribe, getLocale)
  return <label className="language-picker">
    <span>{text('language.label')}</span>
    <select id={id} value={locale} onChange={event => setLocale(event.target.value)} aria-label={text('language.label')}>
      {availableLanguages().map(language => <option key={language.id} value={language.id} lang={language.id}>{language.name}</option>)}
    </select>
  </label>
}

// 经典脚本拥有动态说明；React 不声明子节点，切语言时不会覆盖引擎写入的内容。
function EngineText({ component: Component, id, className, initialKey }) {
  const initialize = useCallback(node => {
    if (node && !node.textContent) node.textContent = text(initialKey)
  }, [initialKey])
  return <Component id={id} className={className} ref={initialize} />
}

// React 只管理外壳。预测引擎独占插槽内的原有 DOM，不复制表单、不重写模型。
function LegacySlot({ node, className = '' }) {
  return <div className={className} ref={host => {
    if (host && node && node.parentNode !== host) host.append(node)
  }} />
}

function ThemeToggle() {
  const [dark, setDark] = useState(document.documentElement.dataset.theme === 'dark')
  function toggle() {
    const next = !dark
    document.documentElement.dataset.theme = next ? 'dark' : 'light'
    try { localStorage.setItem('gc_theme', next ? 'dark' : 'light') } catch {}
    document.querySelector('meta[name="theme-color"]').content = next ? '#15211d' : '#f3f5f4'
    setDark(next)
  }
  return <Button variant="tertiary" size="sm" onPress={toggle} aria-label={text(dark ? 'theme.toLight' : 'theme.toDark')} className="theme-button">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      {dark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></> : <path d="M20.5 14A8.6 8.6 0 0 1 10 3.5 8.7 8.7 0 1 0 20.5 14Z" />}
    </svg>
    <span>{text(dark ? 'theme.light' : 'theme.dark')}</span>
  </Button>
}

function Dashboard({ nodes }) {
  useSyncExternalStore(subscribe, getLocale)
  return <>
    {createPortal(<LanguageSelect id="welcome-language-select" />, document.getElementById('welcome-language'))}
    <a className="skip-link" href="#forecast-workspace" onClick={event => {
      const target = document.getElementById('forecast-workspace')
      if (target) {
        event.preventDefault()
        target.focus()
        target.scrollIntoView({ block: 'start' })
      }
    }}>{text('app.skip')}</a>
    <header className="workspace-header">
      <a className="brand" href="./" aria-label={text('app.brandLabel')}>
        <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 28 28" fill="none"><path d="M6 18v-8m8 12V6m8 12v-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /><circle cx="14" cy="14" r="3" fill="currentColor" /></svg></span>
        <span className="brand-name">GC<span>TIME</span></span>
        <span className="brand-caption">{text('app.brand')}</span>
      </a>
      <div className="header-tools"><span className="data-badge">{text('app.local')}</span><LanguageSelect id="language-select" /><ThemeToggle /></div>
    </header>
    <div className="app workspace">
      <div className="page-heading"><LegacySlot node={nodes.topbar} /></div>
      <div className="workspace-grid">
        <aside className="profile-rail" aria-label={text('shell.conditions')}>
          <Widget className="profile-widget">
            <Widget.Header><div><Widget.Title>{text('shell.profile')}</Widget.Title><Widget.Description>{text('shell.profileDescription')}</Widget.Description></div></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.profile} /></Widget.Content>
            <Widget.Footer><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>{text('shell.private')}</Widget.Footer>
          </Widget>
          <div className="rail-guide">
            <span className="eyebrow">{text('shell.guide')}</span>
            <p><b>{text('shell.tableA')}</b><span>{text('shell.tableADescription')}</span></p>
            <p><b>{text('shell.tableB')}</b><span>{text('shell.tableBDescription')}</span></p>
            <div className="rail-disclaimer">{text('shell.disclaimer')}</div>
          </div>
        </aside>
        <main id="forecast-workspace" className="forecast-workspace" tabIndex="-1">
          <div className="forecast-sheet">
          <Widget className="forecast-widget">
            <Widget.Header className="sr-only"><Widget.Title>{text('shell.forecast')}</Widget.Title></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.result} /></Widget.Content>
          </Widget>
          <Widget className="chart-widget">
            <Widget.Header><div><Widget.Title>{text('shell.chart')}</Widget.Title><EngineText component={Widget.Description} id="chart-description" initialKey="shell.chartDescription" /></div><span className="model-label">{text('shell.simulations', { count: 500 })}</span></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.chart} /></Widget.Content>
          </Widget>
          </div>
          <Widget className="details-widget">
            <Widget.Header><Widget.Title>{text('shell.details')}</Widget.Title><EngineText component="span" id="bulletin-version" className="model-label" initialKey="tab.bulletin" /></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.tabs} /></Widget.Content>
          </Widget>
        </main>
      </div>
      <LegacySlot node={nodes.footer} />
      <LegacySlot node={nodes.table} />
    </div>
  </>
}

const source = document.querySelector('.app')
const nodes = {
  topbar: source.querySelector('.topbar'),
  profile: source.querySelector('#profile-edit'),
  result: source.querySelector('.result'),
  chart: source.querySelector('.chart-panel'),
  tabs: source.querySelector('.gc-tabs'),
  footer: source.querySelector('.footer'),
  table: source.querySelector('table')
}
const root = document.createElement('div')
root.id = 'gc-root'
root.dataset.ui = 'heroui-pro'
source.before(root)
// 在后续经典脚本运行前完成迁移，所有 ID / 全局函数 / 数据机器人契约保持不变。
flushSync(() => createRoot(root).render(<Dashboard nodes={nodes} />))
source.remove()
