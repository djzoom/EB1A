const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')
const { pathToFileURL } = require('node:url')
const { execFileSync } = require('node:child_process')

const locales = ['zh-CN', 'hi', 'es', 'pt-BR', 'ja', 'ko', 'ar', 'de', 'fr', 'it']
const profile = {
  pd: Date.UTC(2026, 0, 15), category: 'EB-1A', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
}
const stripBidi = value => value.replace(/[\u2066-\u2069]/g, '')
const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors, '语言切换不应产生页面异常或缺失翻译').toEqual([])
  }
})

async function catalog(locale) {
  return (await import(pathToFileURL(resolve('src/i18n.js')).href)).catalogs[locale]
}

async function openSaved(page, locale, url = './', category = profile.category) {
  await page.addInitScript(({ saved, locale }) => {
    if (!localStorage.getItem('eb1a_user_profile')) localStorage.setItem('eb1a_user_profile', JSON.stringify(saved))
    if (locale && !localStorage.getItem('gc_language')) localStorage.setItem('gc_language', locale)
  }, { saved: { ...profile, category }, locale })
  await page.goto(url)
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#hero-value')).not.toHaveText('--')
}

async function selectLocale(page, locale, picker = '#language-select') {
  await page.locator(picker).selectOption(locale)
  await expect(page.locator('html')).toHaveAttribute('lang', locale)
  await expect(page.locator(picker)).toHaveValue(locale)
  // 等待 React 外壳与经典脚本同一轮更新，以及 ResizeObserver 的图表重绘。
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
}

async function visibleChinese(page, selector) {
  return page.locator(selector).evaluateAll(elements => elements
    .filter(element => element.getClientRects().length)
    .map(element => element.innerText)
    .join('\n').match(/[\u3400-\u9fff]+/g) || [])
}

async function hoverForecast(page) {
  await page.locator('#chart').scrollIntoViewIfNeeded()
  const target = await page.locator('#chart').evaluate(svg => {
    const bounds = chartBounds
    const candidates = lastSnapData.tables.A.p50
      .filter(point => point.x > bounds.xMin && point.x < bounds.xMax && point.y > bounds.yMin && point.y < bounds.yMax &&
        (chartMode !== 'wait' || point.x > Math.max(lastSnapData.tables.A.cutoff, lastSnapData.tables.B.cutoff)))
    const point = candidates[Math.floor(candidates.length / 2)]
    if (!point) throw new Error('测试需要可见预测数据点')
    const coords = svg.createSVGPoint()
    coords.x = bounds.PAD.left + (point.x - bounds.xMin) / (bounds.xMax - bounds.xMin) * bounds.PW
    coords.y = bounds.PAD.top + (1 - (point.y - bounds.yMin) / (bounds.yMax - bounds.yMin)) * bounds.PH
    const screen = coords.matrixTransform(svg.getScreenCTM())
    return { x: screen.x, y: screen.y }
  })
  await page.mouse.move(target.x, target.y)
  await expect(page.locator('#chart-tooltip')).toBeVisible()
}

test('all ten bundled catalogs have the same complete keys and interpolation contracts', async () => {
  const { catalogs, languages, availableLanguages, validateCatalog, t } = await import(pathToFileURL(resolve('src/i18n.js')).href)
  expect(languages.map(language => language.id)).toEqual(locales)
  expect(availableLanguages().map(language => language.id)).toEqual(locales)
  const keys = Object.keys(catalogs['zh-CN']).sort()
  expect(keys.length).toBeGreaterThanOrEqual(349)
  for (const locale of locales) {
    expect(Object.keys(catalogs[locale]).sort(), locale).toEqual(keys)
    expect(validateCatalog(catalogs[locale]), locale).toEqual([])
    if (!['zh-CN', 'ja'].includes(locale)) {
      const untranslated = Object.entries(catalogs[locale]).filter(([, message]) => /[\u3400-\u9fff]/.test(message)).map(([key]) => key)
      expect(untranslated, `${locale} 不应退回中文词条`).toEqual([])
    }
  }
  const broken = { ...catalogs['zh-CN'], 'app.title': 'Missing scope', extra: 'Unknown' }
  delete broken['welcome.title']
  expect(validateCatalog(broken)).toEqual(expect.arrayContaining([
    'Placeholder mismatch: app.title', 'Missing message: welcome.title', 'Unknown message: extra'
  ]))
  expect(t('app.title', { scope: '<img src=x onerror=alert(1)>' })).toContain('&lt;img src=x onerror=alert(1)&gt;')
  expect(() => t('app.title')).toThrow('Missing i18n parameter')
  expect(() => t('missing.message')).toThrow('Unknown i18n message')
})

for (const locale of locales) {
  test(`${locale} localizes initial, dynamic, accessible and parameter-source text`, async ({ page }) => {
    const messages = await catalog(locale)
    await page.setViewportSize({ width: 1440, height: 1000 })
    await openSaved(page, locale)
    await expect(page.locator('html')).toHaveAttribute('lang', locale)
    await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr')
    await expect(page.locator('#language-select option')).toHaveCount(10)
    await expect(page.locator('#share-btn')).toHaveAccessibleName(messages['action.share'])
    await expect(page.locator('#refresh-btn')).toHaveAttribute('title', messages['action.refreshTitle'])
    await expect(page.locator('#pe-pd-y')).toHaveAttribute('aria-label', messages['profile.editYearLabel'])
    await expect(page.locator('#pe-co option:checked')).toHaveText(messages['country.CN'])
    await expect(page.locator('#ab-status .ab-chip').first()).toContainText(messages['result.tableA'])
    await expect(page.locator('#chart-description')).toHaveText(messages['chart.description'])
    for (const table of ['A', 'B']) {
      await expect(page.locator(`#chart-legend [data-series="forecast-${table}-p50"]`)).toHaveText(
        messages['chart.legendPrediction'].replace('{table}', messages['bulletin.chart'].replace('{chart}', table)))
    }
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart-description')).toHaveText(messages[mode === 'wait' ? 'chart.waitDescription' : 'chart.description'])
      await hoverForecast(page)
      await expect(page.locator('#chart-tooltip .tt-hdr')).toContainText(messages[mode === 'wait' ? 'chart.waitComparisonHeading' : 'chart.comparisonHeading'])
      for (const table of ['A', 'B']) {
        const section = page.locator(`#chart-tooltip section[data-table="${table}"]`)
        await expect(section.locator('.tt-label')).toContainText(messages[`chart.table${table}`])
        await expect(section.locator('.tt-sname')).toHaveText([
          messages['result.optimistic'], messages['result.median'], messages['result.conservative']
        ])
      }
    }
    await page.locator('[data-tab="settings"]').click()
    await expect(page.locator('[data-pace="recent"]')).toHaveText(messages['pace.recent'])
    await page.locator('[data-pace="recent"]').click()
    await expect(page.locator('#pace-note')).toContainText(messages['pace.recentNote'].replace(/<[^>]+>/g, ''))
    await page.locator('#param-row-familyMultiplier .param-name').click()
    await expect(page.locator('#source-familyMultiplier')).toBeVisible()
    await expect(page.locator('#source-familyMultiplier .sp-title')).toHaveText(messages['source.familyTitle'])
    await expect(page.locator('#source-familyMultiplier')).toContainText(messages['param.sources'])
    if (!['zh-CN', 'ja'].includes(locale)) {
      expect(await visibleChinese(page, '#app-title, #app-sub, #hero-sub, #ab-status, #chart-description, #chart-legend, #tab-settings, .footer')).toEqual([])
      for (const tab of ['explain', 'bulletin']) {
        await page.locator(`[data-tab="${tab}"]`).click()
        expect(await visibleChinese(page, `#tab-${tab}`), `${locale} ${tab}`).toEqual([])
      }
    }
  })
}

test('switching every locale preserves drafts, selections, model objects and RNG without resimulation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await openSaved(page)
  await page.locator('[data-pct="p90"]').click()
  await page.locator('#mode-wait').click()
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="recent"]').click()
  await page.locator('[data-sc="tight"]').click()
  await page.locator('#familyMultiplier').evaluate(input => {
    input.value = '2.4'
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect.poll(() => page.evaluate(() => currentParams.familyMultiplier)).toBe(2.4)
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await page.locator('#pe-cat').selectOption('EB-2')
  await page.locator('#pe-co').selectOption('IN')
  await page.locator('#pe-pd-y').fill('2025')
  await page.locator('#pe-pd-m').fill('03')
  await page.locator('#pe-pd-d').fill('07')
  const before = await page.evaluate(() => {
    window.localeTest = {
      paths: lastPercentiles, cloud: lastCloudPaths, crossings: crossingsByPct, crossingsB: crossingsByPctB,
      params: currentParams, rng: _rngState, panel: window._panelPct,
      counts: { render: 0, activateModel: 0, monteCarlo: 0, simulate: 0, seedRng: 0, replayDeduction: 0 }
    }
    for (const name of Object.keys(localeTest.counts)) {
      const original = window[name]
      window[name] = function () { localeTest.counts[name]++; return original.apply(this, arguments) }
    }
    return JSON.stringify({ profile, params: currentParams, paths: lastPercentiles,
      crossings: [crossingsByPct, crossingsByPctB], pace: paceMode,
      percentile: selectedPercentile, supply: supplyScenario, mode: chartMode,
      stored: localStorage.getItem('eb1a_user_profile') })
  })
  for (const locale of [...locales.slice(1), 'zh-CN']) {
    await selectLocale(page, locale)
    await expect(page.locator('#pe-cat')).toHaveValue('EB-2')
    await expect(page.locator('#pe-co')).toHaveValue('IN')
    await expect(page.locator('#pe-pd-y')).toHaveValue('2025')
    await expect(page.locator('#pe-pd-m')).toHaveValue('03')
    await expect(page.locator('#pe-pd-d')).toHaveValue('07')
    await expect(page.locator('#tab-settings')).toHaveClass(/active/)
    await expect(page.locator('[data-pct="p90"]')).toHaveClass(/selected/)
    await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
    await expect(page.locator('[data-sc="tight"]')).toHaveClass(/active/)
    await expect(page.locator('#familyMultiplier')).toHaveValue('2.4')
    const state = await page.evaluate(() => ({
      serialized: JSON.stringify({ profile, params: currentParams, paths: lastPercentiles,
        crossings: [crossingsByPct, crossingsByPctB], pace: paceMode,
        percentile: selectedPercentile, supply: supplyScenario, mode: chartMode,
        stored: localStorage.getItem('eb1a_user_profile') }),
      identities: [lastPercentiles === localeTest.paths, lastCloudPaths === localeTest.cloud,
        crossingsByPct === localeTest.crossings, crossingsByPctB === localeTest.crossingsB,
        currentParams === localeTest.params, window._panelPct === localeTest.panel, _rngState === localeTest.rng],
      counts: localeTest.counts
    }))
    expect(state.serialized, locale).toBe(before)
    expect(state.identities.every(Boolean), locale).toBe(true)
    expect(Object.values(state.counts).every(count => count === 0), `${locale}: ${JSON.stringify(state.counts)}`).toBe(true)
  }
})

test('welcome language is usable before a profile exists and preserves date and queue drafts', async ({ page }) => {
  await page.goto('./')
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  await expect(page.locator('#welcome-modal')).toBeVisible()
  await selectLocale(page, 'de', '#welcome-language-select')
  await page.locator('#wf-cat').selectOption('EB-3')
  await page.locator('#wf-co').selectOption('IN')
  await page.locator('#wf-pd-y').fill('2024')
  await page.locator('#wf-pd-m').fill('02')
  await page.locator('#wf-pd-d').fill('29')
  await page.evaluate(() => {
    window.welcomeLocaleState = { simulations: 0, rng: _rngState, panel: window._panelPct }
    const original = simulate
    window.simulate = function () { welcomeLocaleState.simulations++; return original.apply(this, arguments) }
  })
  await selectLocale(page, 'ar', '#welcome-language-select')
  await expect(page.locator('#wf-title')).toHaveText((await catalog('ar'))['welcome.title'])
  await expect(page.locator('#wf-cat')).toHaveValue('EB-3')
  await expect(page.locator('#wf-co')).toHaveValue('IN')
  await expect(page.locator('#wf-pd-y')).toHaveValue('2024')
  await expect(page.locator('#wf-pd-m')).toHaveValue('02')
  await expect(page.locator('#wf-pd-d')).toHaveValue('29')
  expect(await page.evaluate(() => ({ simulations: welcomeLocaleState.simulations,
    rng: _rngState === welcomeLocaleState.rng, panel: window._panelPct === welcomeLocaleState.panel })))
    .toEqual({ simulations: 0, rng: true, panel: true })
  await page.locator('#wf-start').click()
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
  await page.reload()
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#language-select')).toHaveValue('ar')
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('eb1a_user_profile')))).toMatchObject({ category: 'EB-3', country: 'IN', pd: Date.UTC(2024, 1, 29) })
})

test('a saved locale localizes the welcome and unconfigured background without generating predictions', async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('gc_language')) localStorage.setItem('gc_language', 'de')
  })
  await page.goto('./')
  const initial = await page.evaluate(() => JSON.stringify({
    params: currentParams, profile, paths: lastPercentiles, cloud: lastCloudPaths,
    crossings: [crossingsByPct, crossingsByPctB], panel: window._panelPct, rng: _rngState
  }))
  expect(JSON.parse(initial)).toMatchObject({
    profile: { pd: null }, paths: null, cloud: null, crossings: [null, null], panel: null, rng: 1
  })
  for (const locale of ['de', ...locales.filter(value => value !== 'de')]) {
    if (locale !== 'de') {
      await selectLocale(page, locale, '#welcome-language-select')
      await page.reload()
    }
    const messages = await catalog(locale)
    await expect(page.locator('#welcome-modal')).toBeVisible()
    await expect(page.locator('#welcome-language-select')).toHaveValue(locale)
    await expect(page.locator('#wf-title')).toHaveText(messages['welcome.title'])
    await expect(page.locator('#wf-start')).toHaveText(messages['welcome.start'])
    await expect(page.locator('#wf-start')).toBeDisabled()
    await expect(page.locator('#hero-sub')).toHaveText(messages['result.fromNow'].replace('{wait}', '--'))
    await expect(page.locator('#chart-description')).toHaveText(messages['chart.description'])
    for (const table of ['A', 'B']) {
      await expect(page.locator(`#chart-legend [data-series="history-${table}"]`)).toHaveText(messages['chart.legendHistory'].replace('{table}', messages[`chart.table${table}`]))
      await expect(page.locator(`#chart-legend [data-series="forecast-${table}-p50"]`)).toHaveText(messages['chart.legendPrediction'].replace('{table}', messages['bulletin.chart'].replace('{chart}', table)))
    }
    expect(await page.evaluate(() => JSON.stringify({
      params: currentParams, profile, paths: lastPercentiles, cloud: lastCloudPaths,
      crossings: [crossingsByPct, crossingsByPctB], panel: window._panelPct, rng: _rngState
    })), locale).toBe(initial)
    expect(await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))).toBeNull()
  }
})

test('unknown saved language safely defaults to Chinese and a manual choice persists', async ({ page }) => {
  await openSaved(page, 'not-a-language')
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  const stored = await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))
  await selectLocale(page, 'fr')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
  await expect(page.locator('#language-select')).toHaveValue('fr')
  expect(await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))).toBe(stored)
})

test('shared language takes precedence without overwriting saved preference and manual choice updates only lang', async ({ page }) => {
  const hash = new URLSearchParams({ share: '1', category: 'EB-3', country: 'IN', pd: '2024-02-29', view: 'B', pace: 'recent', percentile: 'p90', lang: 'ar' })
  await openSaved(page, 'fr', `./#${hash}`)
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBe('fr')
  const before = [...new URLSearchParams(new URL(page.url()).hash.slice(1))].filter(([key]) => key !== 'lang')
  await selectLocale(page, 'it')
  const after = new URLSearchParams(new URL(page.url()).hash.slice(1))
  expect([...after].filter(([key]) => key !== 'lang')).toEqual(before)
  expect(after.get('lang')).toBe('it')
  await expect(page.locator('#shared-notice')).toHaveText((await catalog('it'))['action.sharedPreview'])
  expect(await page.evaluate(() => ({ language: localStorage.getItem('gc_language'), saved: JSON.parse(localStorage.getItem('eb1a_user_profile')) })))
    .toEqual({ language: 'it', saved: profile })
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('lang', 'it')
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
})

test('copy feedback and fallback are translated while shared conditions and language remain reproducible', async ({ page }) => {
  await page.addInitScript(() => {
    window.localeCopies = []
    window.rejectLocaleCopy = false
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async value => {
        localeCopies.push(value)
        if (rejectLocaleCopy) throw new DOMException('Clipboard denied', 'NotAllowedError')
      }
    } })
    document.execCommand = () => false
  })
  await openSaved(page, 'fr')
  await page.locator('#share-btn').click()
  await expect(page.locator('#action-status')).toHaveText((await catalog('fr'))['action.sharedCopied'])
  const snapshot = new URLSearchParams(new URL(await page.evaluate(() => localeCopies.at(-1))).hash.slice(1))
  expect(Object.fromEntries(['category', 'country', 'pd', 'lang'].map(key => [key, snapshot.get(key)])))
    .toEqual({ category: 'EB-1', country: 'CN', pd: '2026-01-15', lang: 'fr' })
  await selectLocale(page, 'ar')
  await expect(page.locator('#action-status')).toHaveText((await catalog('ar'))['action.sharedCopied'])
  await page.evaluate(() => { rejectLocaleCopy = true })
  await page.locator('#share-btn').click()
  await expect(page.locator('#action-status')).toHaveText((await catalog('ar'))['action.copyFailed'])
  await expect(page.locator('#share-url')).toBeVisible()
  await expect(page.locator('#share-url')).toHaveAccessibleName((await catalog('ar'))['action.manualCopy'])
  expect(await page.locator('#share-url').evaluate(input => getComputedStyle(input).direction)).toBe('ltr')
  expect(new URLSearchParams(new URL(await page.locator('#share-url').inputValue()).hash.slice(1)).get('lang')).toBe('ar')
  await expect(page.locator('#share-btn svg')).toHaveCount(1)
})

test('Arabic, Persian and Devanagari date digits retain Gregorian year-month-day order and an LTR time axis', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await openSaved(page, 'ar')
  for (const digits of [['٢٠٢٤', '٠٢', '٢٩'], ['۲۰۲۴', '۰۲', '۲۹'], ['२०२४', '०२', '२९']]) {
    await page.locator('#pe-pd-y').fill(digits[0])
    await page.locator('#pe-pd-m').fill(digits[1])
    await page.locator('#pe-pd-d').fill(digits[2])
    await expect(page.locator('#pe-pd-y')).toHaveValue('2024')
    await expect(page.locator('#pe-pd-m')).toHaveValue('02')
    await expect(page.locator('#pe-pd-d')).toHaveValue('29')
  }
  const geometry = await page.evaluate(() => {
    const inputs = ['pe-pd-y', 'pe-pd-m', 'pe-pd-d'].map(id => document.getElementById(id).getBoundingClientRect().x)
    const svg = document.getElementById('chart')
    const axis = [...svg.querySelectorAll('text')]
      .filter(label => Math.abs(Number(label.getAttribute('y')) - (chartBounds.PAD.top + chartBounds.PH + 16)) < 1)
      .map(label => ({ x: Number(label.getAttribute('x')), label: label.textContent }))
    return { inputs, direction: getComputedStyle(svg).direction, matrix: svg.getScreenCTM().a, axis }
  })
  expect(geometry.inputs[0]).toBeLessThan(geometry.inputs[1])
  expect(geometry.inputs[1]).toBeLessThan(geometry.inputs[2])
  expect(geometry.direction).toBe('ltr')
  expect(geometry.matrix).toBeGreaterThan(0)
  expect(geometry.axis.length).toBeGreaterThanOrEqual(2)
  for (let index = 1; index < geometry.axis.length; index++) expect(geometry.axis[index].x).toBeGreaterThan(geometry.axis[index - 1].x)
  await page.locator('#pe-save').click()
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
  expect(await page.evaluate(() => new Date(profile.pd).toISOString().slice(0, 10))).toBe('2024-02-29')
  await page.locator('#pe-pd-d').fill('٣١')
  await page.locator('#pe-save').click()
  await expect(page.locator('#pe-err')).toBeVisible()
  await expect(page.locator('#pe-err')).toHaveText((await catalog('ar'))['profile.invalidDate'])
  await selectLocale(page, 'hi')
  await expect(page.locator('#pe-err')).toHaveText((await catalog('hi'))['profile.invalidDate'])
  await expect(page.locator('#pe-pd-d')).toHaveValue('31')
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
})

test('Arabic cutoff dates and forecast ranges keep visual YYYY-MM order without changing shared ASCII dates', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async value => { window.bidiCopiedLink = value }
    } })
  })
  await openSaved(page)
  const original = await page.locator('.ab-cutoff b, .ab-range').allTextContents()
  await selectLocale(page, 'ar')
  expect((await page.locator('.ab-cutoff b, .ab-range').allTextContents()).map(stripBidi)).toEqual(original)
  const geometry = await page.locator('.ab-cutoff b, .ab-range').evaluateAll(elements => {
    function textGeometry(element) {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
      const nodes = []
      let node
      while ((node = walker.nextNode())) nodes.push(node)
      const text = nodes.map(node => node.textContent).join('')
      function locate(offset) {
        for (const node of nodes) {
          if (offset < node.textContent.length) return { node, offset }
          offset -= node.textContent.length
        }
        return { node: nodes.at(-1), offset: nodes.at(-1).textContent.length }
      }
      function rect(start, length) {
        const first = locate(start), last = locate(start + length)
        const range = document.createRange()
        range.setStart(first.node, first.offset)
        range.setEnd(last.node, last.offset)
        const box = range.getBoundingClientRect()
        return { left: box.left, right: box.right, top: box.top }
      }
      return [...text.matchAll(/[0-9]{4}-[0-9]{2}/g)].map(match => ({
        date: match[0], year: rect(match.index, 4), month: rect(match.index + 5, 2), all: rect(match.index, 7)
      }))
    }
    return elements.map(element => ({ range: element.classList.contains('ab-range'), dates: textGeometry(element) }))
  })
  expect(geometry).toHaveLength(4)
  for (const element of geometry) {
    expect(element.dates).toHaveLength(element.range ? 2 : 1)
    for (const date of element.dates) {
      expect(date.year.left, date.date).toBeLessThan(date.month.left)
      expect(Math.abs(date.year.top - date.month.top), date.date).toBeLessThan(1)
    }
    if (element.range) expect(element.dates[0].all.right).toBeLessThan(element.dates[1].all.left)
  }
  await page.locator('#share-btn').click()
  await expect.poll(() => page.evaluate(() => typeof window.bidiCopiedLink)).toBe('string')
  const fragment = new URLSearchParams(new URL(await page.evaluate(() => bidiCopiedLink)).hash.slice(1))
  expect(fragment.get('pd')).toBe('2026-01-15')
  expect(fragment.get('lang')).toBe('ar')
})

test('Current results remain localized without creating simulation paths', async ({ page }) => {
  await openSaved(page, 'de', './', 'EB-5-Rural')
  for (const locale of ['de', 'ar', 'ja', 'zh-CN']) {
    await selectLocale(page, locale)
    const messages = await catalog(locale)
    await expect(page.locator('#hero-value')).toHaveText(messages['result.current'])
    await expect(page.locator('#hero-sub')).toHaveText(messages['result.noWait'])
    await expect(page.locator('.chart-widget')).toBeHidden()
    expect(await page.evaluate(() => lastPercentiles)).toBeNull()
    await expect.poll(async () => stripBidi(await page.locator('#congrats-pd').textContent())).toBe('2026-01')
    await expect(page.locator('#pv-pd')).toHaveText('2026-01-15')
    await expect(page.locator('#footer-scope')).toHaveCount(1)
  }
})

for (const width of [375, 768, 1440, 1920]) {
  test(`all locales fit the ${width}px workspace and settings without horizontal overflow`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await openSaved(page)
    for (const locale of locales) {
      await selectLocale(page, locale)
      // 可选视觉证据留在调用方指定的临时目录，不生成仓库内基准截图。
      if (process.env.GCTIME_VISUAL_DIR &&
        ((width === 1440 && ['zh-CN', 'de', 'ar'].includes(locale)) ||
          (width === 375 && ['hi', 'ar'].includes(locale)))) {
        await page.locator('[data-tab="bulletin"]').click()
        await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo({ top: 0, behavior: 'instant' }) })
        await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
        await page.screenshot({ path: resolve(process.env.GCTIME_VISUAL_DIR, `${locale}-${width}.png`), fullPage: true })
      }
      for (const tab of ['bulletin', 'settings']) {
        await page.locator(`[data-tab="${tab}"]`).click()
        expect(await page.evaluate(() => document.documentElement.scrollWidth), `${locale} / ${tab} / ${width}`).toBeLessThanOrEqual(width)
      }
      const header = await page.locator('.workspace-header').boundingBox()
      const picker = await page.locator('#language-select').boundingBox()
      expect(picker.x, locale).toBeGreaterThanOrEqual(header.x - 1)
      expect(picker.x + picker.width, locale).toBeLessThanOrEqual(header.x + header.width + 1)
      for (const table of ['A', 'B']) {
        const card = page.locator(`#ab-status .ab-chip[data-table="${table}"]`)
        await expect(card.locator('.ab-pred em')).toBeVisible()
        const date = await card.locator('.ab-pred em').boundingBox()
        const result = await card.boundingBox()
        expect(date.x, `${locale} ${table}`).toBeGreaterThanOrEqual(result.x - 1)
        expect(date.x + date.width, `${locale} ${table}`).toBeLessThanOrEqual(result.x + result.width + 1)
      }
    }
  })
}

test('single HTML includes all languages and can switch them completely offline', async ({ page, context }) => {
  const requests = []
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()) })
  await context.setOffline(true)
  await openSaved(page, undefined, pathToFileURL(resolve('dist/EB1A.html')).href)
  for (const locale of locales) {
    await selectLocale(page, locale)
    const messages = await catalog(locale)
    await expect(page.locator('#share-btn')).toHaveAccessibleName(messages['action.share'])
    await expect(page.locator('#language-select option')).toHaveCount(10)
    const notice = await page.evaluate(() => GCI18n.text('offline.notice', { month: GCI18n.formatMonth(VB_YEAR, VB_MON) }))
    await expect(page.locator('.footer')).toContainText(notice)
    await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
  }
  expect(requests).toEqual([])
})

test('the offline ZIP includes Chinese instructions and every bundled language without missing translations', async () => {
  const { catalogs, languages } = await import(pathToFileURL(resolve('src/i18n.js')).href)
  const archive = JSON.parse(execFileSync('python3', ['-c', [
    'import json, sys, zipfile',
    'with zipfile.ZipFile(sys.argv[1]) as archive:',
    '    print(json.dumps({"files": archive.namelist(), "readme": archive.read("README-languages.txt").decode("utf-8"), "chinese": archive.read("使用说明.txt").decode("utf-8")}))'
  ].join('\n'), resolve('dist/EB1A-offline.zip')], { encoding: 'utf8' }))
  expect(archive.files.sort()).toEqual(['EB1A.html', 'README-languages.txt', '使用说明.txt'].sort())
  expect(archive.chinese).toBe(catalogs['zh-CN']['offline.readme'] + '\n')
  expect(archive.readme).toBe(languages.map(({ id, name }) => `${name} (${id})\n${catalogs[id]['offline.readme']}`).join('\n\n') + '\n')
})
