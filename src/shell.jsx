import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { Widget } from '@heroui-pro/react/widget'
import { Button } from '@heroui/react/button'

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
  return <Button variant="tertiary" size="sm" onPress={toggle} aria-label={dark ? '切换浅色模式' : '切换深色模式'} className="theme-button">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      {dark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></> : <path d="M20.5 14A8.6 8.6 0 0 1 10 3.5 8.7 8.7 0 1 0 20.5 14Z" />}
    </svg>
    <span>{dark ? '浅色' : '深色'}</span>
  </Button>
}

function Dashboard({ nodes }) {
  return <>
    <a className="skip-link" href="#forecast-workspace">跳到预测结果</a>
    <header className="workspace-header">
      <a className="brand" href="./" aria-label="GC Time 绿卡排期工作台">
        <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 28 28" fill="none"><path d="M6 18v-8m8 12V6m8 12v-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /><circle cx="14" cy="14" r="3" fill="currentColor" /></svg></span>
        <span className="brand-name">GC<span>TIME</span></span>
        <span className="brand-caption">绿卡排期工作台</span>
      </a>
      <div className="header-tools"><span className="data-badge"><i />公开数据 · 本地计算</span><ThemeToggle /></div>
    </header>
    <div className="app workspace">
      <div className="page-heading"><LegacySlot node={nodes.topbar} /></div>
      <div className="workspace-grid">
        <aside className="profile-rail" aria-label="预测条件">
          <Widget className="profile-widget">
            <Widget.Header><div><Widget.Title>我的档案</Widget.Title><Widget.Description>选择你的排期队列</Widget.Description></div><span className="section-index">01</span></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.profile} /></Widget.Content>
            <Widget.Footer><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>仅保存在你的浏览器</Widget.Footer>
          </Widget>
          <div className="rail-guide">
            <span className="eyebrow">读懂你的排期</span>
            <p><b>表 A · 最终裁定</b><span>何时可以获批绿卡</span></p>
            <p><b>表 B · 递交申请</b><span>何时可能递交 I-485</span></p>
            <div className="rail-disclaimer">预测是参考，不是承诺。<br />请以 DOS / USCIS 官方公告为准。</div>
          </div>
        </aside>
        <main id="forecast-workspace" className="forecast-workspace" tabIndex="-1">
          <Widget className="forecast-widget">
            <Widget.Header><Widget.Title>你的排期预测</Widget.Title><span className="model-label">蒙特卡洛 · 500 次模拟</span></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.result} /></Widget.Content>
          </Widget>
          <Widget className="chart-widget">
            <Widget.Header><div><Widget.Title>排期走势</Widget.Title><Widget.Description>历史走到哪里，未来可能怎样</Widget.Description></div><span className="section-index">02</span></Widget.Header>
            <Widget.Content><LegacySlot node={nodes.chart} /></Widget.Content>
          </Widget>
          <Widget className="details-widget">
            <Widget.Header><Widget.Title>数据与假设</Widget.Title><span id="bulletin-version" className="model-label">签证公告</span></Widget.Header>
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
