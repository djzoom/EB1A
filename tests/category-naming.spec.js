const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')
const { pathToFileURL } = require('node:url')

const profileKey = 'eb1a_user_profile'
const locales = ['zh-CN', 'hi', 'es', 'pt-BR', 'ja', 'ko', 'ar', 'de', 'fr', 'it']
const savedProfile = {
  pd: Date.UTC(2026, 0, 15), category: 'EB-1A', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
}

const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      window.categoryCopies = []
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: async value => { window.categoryCopies.push(value) } }
      })
    })
    await use(page)
    expect(errors, '类别别名、保存和分享不应产生页面异常').toEqual([])
  }
})

test.use({ locale: 'zh-CN' })

async function seedProfile(page, country = 'CN', category = 'EB-1A') {
  const saved = { ...savedProfile, country, category }
  await page.addInitScript(({ key, saved }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(saved))
  }, { key: profileKey, saved })
  return saved
}

async function expectReady(page) {
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#hero-value')).not.toHaveText('--')
}

async function copyLink(page) {
  const count = await page.evaluate(() => categoryCopies.length)
  await page.locator('#share-btn').click()
  await expect.poll(() => page.evaluate(() => categoryCopies.length)).toBe(count + 1)
  return page.evaluate(() => categoryCopies.at(-1))
}

async function modelSnapshot(page) {
  return page.evaluate(() => ({
    category: profile.category, country: profile.country, pd: profile.pd,
    model: activeModel().key, status: cellStatus(), params: { ...currentParams },
    cutoffA: cutoffRaw(profile.category, profile.country, 'A'),
    cutoffB: cutoffRaw(profile.category, profile.country, 'B'),
    historyA: histA(), historyB: histB(),
    paths: lastPercentiles, crossingA: crossingsByPct, crossingB: crossingsByPctB
  }))
}

function shareHash(category, country) {
  return '#' + new URLSearchParams({ share: '1', category, country, pd: '2026-01-15', lang: 'zh-CN' })
}

test('first visit has one canonical EB-1 category defined only as exceptional talent', async ({ page }) => {
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeVisible()
  await expect(page.locator('#wf-cat')).toHaveValue('EB-1')
  await expect(page.locator('#wf-cat option[value="EB-1"]')).toHaveText('EB-1 杰出人才')
  await expect(page.locator('#wf-cat option[value="EB-1A"]')).toHaveCount(0)
  await expect(page.locator('#wf-cat option')).toHaveCount(8)
  expect(await page.locator('#welcome-modal').innerText()).not.toMatch(/EB-1A|教授|高管/)
})

for (const country of ['CN', 'IN', 'ROW']) {
  test(`legacy EB-1A ${country} profile is normalized in memory without rewriting saved data`, async ({ page }) => {
    const saved = await seedProfile(page, country)
    await page.goto('./')
    await expectReady(page)
    await expect(page.locator('#app-title')).toHaveText('EB-1 排期推演')
    await expect(page.locator('#pe-cat')).toHaveValue('EB-1')
    await expect(page.locator('#pe-cat option:checked')).toHaveText('EB-1 杰出人才')
    expect(await page.evaluate(key => ({ active: profile.category, stored: localStorage.getItem(key) }), profileKey))
      .toEqual({ active: 'EB-1', stored: JSON.stringify(saved) })
    const data = await page.evaluate(country => ({
      a: JSON.stringify(histFor('EB-1', country, 'A')) === JSON.stringify(histFor('EB-1A', country, 'A')),
      b: JSON.stringify(histFor('EB-1', country, 'B')) === JSON.stringify(histFor('EB-1A', country, 'B')),
      cutoffA: cutoffRaw('EB-1', country, 'A') === cutoffRaw('EB-1A', country, 'A'),
      cutoffB: cutoffRaw('EB-1', country, 'B') === cutoffRaw('EB-1A', country, 'B'),
      historyCount: [histA().length, histB().length],
      finite: !lastPercentiles || Object.values(lastPercentiles).every(path => path.every(point => Number.isFinite(point.x) && Number.isFinite(point.y)))
    }), country)
    expect(data).toMatchObject({ a: true, b: true, cutoffA: true, cutoffB: true, finite: true })
    expect(data.historyCount.every(count => count > 0)).toBe(true)
    await page.locator('[data-tab="settings"]').click()
    expect(await page.locator('#tab-settings').innerText()).not.toMatch(/EB-1A|教授|高管/)
    expect(await page.locator('#params-container').textContent()).not.toMatch(/EB-1A|教授|高管/)
    for (const tab of ['explain', 'bulletin']) {
      await page.locator(`[data-tab="${tab}"]`).click()
      expect(await page.locator(`#tab-${tab}`).innerText()).not.toMatch(/EB-1A|教授|高管/)
    }
    expect(await page.locator('.footer').innerText()).not.toContain('EB-1A')
    if (country === 'ROW') {
      await expect(page.locator('#hero-value')).toHaveText('Current')
      await expect(page.locator('.chart-panel')).toBeHidden()
    } else {
      await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
    }
    await page.reload()
    await expectReady(page)
    await expect(page.locator('#pe-cat')).toHaveValue('EB-1')
    expect(await page.evaluate(key => localStorage.getItem(key), profileKey)).toBe(JSON.stringify(saved))
  })

  test(`legacy and canonical EB-1 ${country} share links give identical data and predictions`, async ({ page }) => {
    const saved = await seedProfile(page, 'MX', 'EB-3')
    await page.goto(`./${shareHash('EB-1A', country)}`)
    await expectReady(page)
    await expect(page.locator('#shared-notice')).toBeVisible()
    await expect(page.locator('#shared-notice')).not.toContainText('无效')
    await expect(page.locator('#pe-cat')).toHaveValue('EB-1')
    const legacy = await modelSnapshot(page)
    expect(legacy.category).toBe('EB-1')
    const copiedLegacy = new URLSearchParams(new URL(await copyLink(page)).hash.slice(1))
    expect(copiedLegacy.get('category')).toBe('EB-1')
    expect(copiedLegacy.get('country')).toBe(country)
    expect(copiedLegacy.get('pd')).toBe('2026-01-15')
    await page.evaluate(() => { window.categoryShareToken = 'legacy-document' })
    await page.goto(`./${shareHash('EB-1', country)}`)
    await page.waitForFunction(() => window.categoryShareToken === undefined)
    await expectReady(page)
    expect(await modelSnapshot(page)).toEqual(legacy)
    expect(await page.evaluate(key => localStorage.getItem(key), profileKey)).toBe(JSON.stringify(saved))
    expect(new URLSearchParams(new URL(await copyLink(page)).hash.slice(1)).get('category')).toBe('EB-1')
  })
}

test('all ten languages show a single EB-1 talent definition without subtype names', async ({ page }) => {
  const { catalogs } = await import(pathToFileURL(resolve('src/i18n.js')).href)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await seedProfile(page, 'IN')
  await page.goto('./')
  await expectReady(page)
  await page.locator('[data-tab="settings"]').click()
  for (const locale of locales) {
    const label = catalogs[locale]['category.EB-1']
    expect(label, locale).toMatch(/^EB-1\s+\S/)
    expect(label, locale).not.toMatch(/EB-1A|\//)
    expect(Object.keys(catalogs[locale]), locale).not.toContain('category.EB-1A')
    expect(Object.keys(catalogs[locale]), locale).not.toContain('source.upstream.EB-1A')
    await page.locator('#language-select').selectOption(locale)
    await expect(page.locator('html')).toHaveAttribute('lang', locale)
    for (const selector of ['#wf-cat', '#pe-cat']) {
      await expect(page.locator(`${selector} option[value="EB-1"]`)).toHaveText(label)
      await expect(page.locator(`${selector} option[value="EB-1A"]`)).toHaveCount(0)
    }
    expect(await page.title(), locale).not.toContain('EB-1A')
    expect(await page.locator('#app-title, #params-container, .footer').allTextContents(), locale)
      .not.toEqual(expect.arrayContaining([expect.stringContaining('EB-1A')]))
  }
})

test('new and explicitly resaved profiles use EB-1 while preserving the legacy storage key', async ({ page }) => {
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeVisible()
  await page.locator('#wf-co').selectOption('IN')
  await page.locator('#wf-pd-y').fill('2026')
  await page.locator('#wf-pd-m').fill('01')
  await page.locator('#wf-pd-d').fill('15')
  await page.locator('#wf-start').click()
  await expectReady(page)
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), profileKey))
    .toMatchObject({ category: 'EB-1', country: 'IN', pd: Date.UTC(2026, 0, 15) })
  await page.reload()
  await expectReady(page)
  await expect(page.locator('#pe-cat')).toHaveValue('EB-1')
  await page.evaluate(({ key, saved }) => { localStorage.setItem(key, JSON.stringify(saved)) }, { key: profileKey, saved: savedProfile })
  await page.reload()
  await expectReady(page)
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).category, profileKey)).toBe('EB-1A')
  await page.locator('#profile-toggle').click()
  await page.locator('#pe-save').click()
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).category, profileKey)).toBe('EB-1')
  await page.reload()
  await expectReady(page)
  await expect(page.locator('#app-title')).toHaveText('EB-1 排期推演')
})

test('only the exact legacy EB-1A alias is accepted and other subtype identifiers stay invalid', async ({ page }) => {
  await seedProfile(page)
  await page.goto('./')
  await expectReady(page)
  const result = await page.evaluate(() => {
    const parse = category => window.GCShare.parse('#' + new URLSearchParams({
      share: '1', category, country: 'CN', pd: '2026-01-15'
    }), CATEGORIES.map(item => item.id), COUNTRIES.map(item => item.id))
    return {
      canonical: parse('EB-1').profile.category,
      legacy: parse('EB-1A').profile.category,
      invalid: ['EB-1B', 'EB-1C', 'EB-1AA', 'eb-1a', '__proto__', 'EB-1<script>'].map(category => parse(category))
    }
  })
  expect(result).toEqual({ canonical: 'EB-1', legacy: 'EB-1', invalid: Array(6).fill({ invalid: true }) })
})

test('offline single HTML applies the same naming and alias compatibility without network requests', async ({ page, context }) => {
  const requests = []
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()) })
  const saved = await seedProfile(page, 'IN')
  await context.setOffline(true)
  await page.goto(pathToFileURL(resolve('dist/EB1A.html')).href)
  await expectReady(page)
  await expect(page.locator('#app-title')).toHaveText('EB-1 排期推演')
  await expect(page.locator('#pe-cat')).toHaveValue('EB-1')
  await expect(page.locator('#pe-cat option:checked')).toHaveText('EB-1 杰出人才')
  await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
  expect(await page.evaluate(key => ({ category: profile.category, stored: localStorage.getItem(key) }), profileKey))
    .toEqual({ category: 'EB-1', stored: JSON.stringify(saved) })
  expect(new URLSearchParams(new URL(await copyLink(page)).hash.slice(1)).get('category')).toBe('EB-1')
  expect(requests).toEqual([])
})
