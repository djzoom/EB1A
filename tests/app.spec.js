const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')
const { pathToFileURL } = require('node:url')

// 每个独立浏览器上下文都收集未捕获异常，包含切换设置时的错误。
const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors, '页面不应出现未捕获的 JavaScript 异常').toEqual([])
  }
})

const categories = ['EB-1A', 'EB-2', 'EB-3', 'EB-4', 'EB-5', 'EB-5-Rural', 'EB-5-HighUnemp', 'EB-5-Infra']
const countries = ['CN', 'IN', 'ROW', 'MX', 'PH']

async function openProfile(page, category = 'EB-1A', country = 'CN', url = './') {
  await page.addInitScript(({ category, country }) => {
    // 仅初始化，重载后保留用户操作；持久化测试不会被初始化脚本覆盖。
    if (!localStorage.getItem('eb1a_user_profile')) {
      localStorage.setItem('eb1a_user_profile', JSON.stringify({
        pd: Date.UTC(2026, 0, 15), category, country, path: 'AOS', family: 0, chartType: 'A'
      }))
    }
  }, { category, country })
  await page.goto(url)
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#hero-value')).not.toHaveText('--')
}

for (const category of categories) {
  for (const country of countries) {
    test(`${category} / ${country} renders both pace modes`, async ({ page }) => {
      await openProfile(page, category, country)
      await page.locator('[data-tab="settings"]').click()
      for (const pace of ['model', 'recent']) {
        await page.locator(`[data-pace="${pace}"]`).click()
        await expect(page.locator(`[data-pace="${pace}"]`)).toHaveClass(/active/)
        await expect(page.locator('#ab-status .ab-chip')).toHaveCount(2)
        const state = await page.evaluate(() => ({
          current: cellStatus() === 'current',
          finite: !lastPercentiles || Object.values(lastPercentiles).every(path =>
            path.length > 0 && path.every(point => Number.isFinite(point.x) && Number.isFinite(point.y)))
        }))
        expect(state.finite).toBe(true)
        if (state.current) {
          await expect(page.locator('#hero-value')).toHaveText('Current')
          await expect(page.locator('#hero-sub')).toHaveText('已 current，无需等待')
          await expect(page.locator('.chart-panel')).toBeHidden()
        } else {
          await expect(page.locator('.chart-panel')).toBeVisible()
          await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
          expect(await page.locator('#chart path').count()).toBeGreaterThan(0)
          expect(await page.locator('#chart').innerHTML()).not.toMatch(/NaN|Infinity/)
        }
        expect(await page.locator('#ab-status').innerText()).not.toMatch(/NaN|Invalid Date|undefined/)
      }
    })
  }
}

test('one percentile selection updates both result cards without rerunning the simulation', async ({ page }) => {
  await openProfile(page)
  await page.evaluate(() => {
    window.dualResultState = { paths: lastPercentiles, cloud: lastCloudPaths, rng: _rngState, calls: 0 }
    const original = monteCarlo
    window.monteCarlo = function () { dualResultState.calls++; return original.apply(this, arguments) }
  })
  for (const percentile of ['p10', 'p90', 'p50']) {
    await page.locator(`[data-pct="${percentile}"]`).click()
    const expected = await page.evaluate(percentile => [
      formatDateFull(crossingsByPct[percentile]), formatDateFull(crossingsByPctB[percentile])
    ], percentile)
    for (const [index, table] of ['A', 'B'].entries()) {
      await expect(page.locator(`#ab-status [data-table="${table}"] .ab-pred em`)).toHaveText(expected[index])
    }
    for (const mode of ['wait', 'trend']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart [data-series="forecast-A-p50"]')).toBeAttached()
      await expect(page.locator('#chart [data-series="forecast-B-p50"]')).toBeAttached()
    }
  }
  await expect(page.locator('#ab-status')).toContainText('表 B 为 DOS 预筛日期')
  expect(await page.evaluate(() => ({
    paths: lastPercentiles === dualResultState.paths, cloud: lastCloudPaths === dualResultState.cloud,
    rng: _rngState === dualResultState.rng, calls: dualResultState.calls
  }))).toEqual({ paths: true, cloud: true, rng: true, calls: 0 })
})

test('pace selection changes the forecast and survives reload and parameter reset', async ({ page }) => {
  await openProfile(page)
  const modelEnd = await page.evaluate(() => lastPercentiles.p50.at(-1).y)
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="recent"]').click()
  const recentEnd = await page.evaluate(() => lastPercentiles.p50.at(-1).y)
  expect(recentEnd).toBeGreaterThan(modelEnd)
  await expect(page.locator('#pace-note')).toContainText('偏乐观')
  await page.reload()
  await page.locator('[data-tab="settings"]').click()
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
  expect(await page.evaluate(() => lastPercentiles.p50.at(-1).y)).toBe(recentEnd)
  await page.locator('[data-sc="tight"]').click()
  await page.locator('#param-reset').click()
  await expect(page.locator('[data-sc="normal"]')).toHaveClass(/active/)
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
  expect(await page.evaluate(() => localStorage.getItem('gc_pace_mode'))).toBe('recent')
  expect(await page.evaluate(() => lastPercentiles.p50.at(-1).y)).toBe(recentEnd)
  await page.reload()
  await page.locator('[data-tab="settings"]').click()
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
  await page.locator('[data-pace="model"]').click()
  await page.reload()
  await page.locator('[data-tab="settings"]').click()
  await expect(page.locator('[data-pace="model"]')).toHaveClass(/active/)
  expect(await page.evaluate(() => lastPercentiles.p50.at(-1).y)).toBe(modelEnd)
})

test('B resumes progress after its hold limit and never moves backwards', async ({ page }) => {
  await openProfile(page, 'EB-3', 'CN')
  const result = await page.evaluate(() => {
    const day = MS_PER_DAY
    const holdEnd = bHoldStart() + bHoldMaxMonths() * 30.44 * day
    const bNow = histB().at(-1).y
    // 构造很慢的表A：自然追赶不足以推动表B，必须由停留上限解除停滞。
    const slowStart = bNow - Math.abs(typicalLead()) - 3650 * day
    const path = Array.from({ length: 60 }, (_, index) => ({
      x: holdEnd + (index - 2) * 31 * day,
      y: slowStart + index * day
    }))
    const projected = projectBPath(path)
    return {
      before: projected.slice(0, 3).map(point => point.y),
      bNow,
      firstAfter: projected[3].y,
      follows: projected.slice(4).every((point, index) => point.y > projected[index + 3].y),
      datesPreserved: projected.every((point, index) => point.x === path[index].x),
      monotonic: projected.every((point, index) => !index || point.y >= projected[index - 1].y),
      capMonths: bHoldMaxMonths()
    }
  })
  expect(result.capMonths).toBeGreaterThan(0)
  expect(result.before).toEqual([result.bNow, result.bNow, result.bNow])
  expect(result.firstAfter).toBeGreaterThan(result.bNow)
  expect(result.follows).toBe(true)
  expect(result.datesPreserved).toBe(true)
  expect(result.monotonic).toBe(true)
})

for (const category of ['EB-1A', 'EB-2', 'EB-3']) {
  test(`${category} China uses the October B fiscal-year anchor`, async ({ page }) => {
    await openProfile(page, category, 'CN')
    const result = await page.evaluate(() => {
      const anchor = fyAnchor()
      const enabled = activeModel().anchor
      if (!anchor) return { enabled, anchor: null }
      const october = histB().find(point => {
        const date = new Date(point.x)
        return date.getUTCFullYear() === anchor.fy - 1 && date.getUTCMonth() === 9
      })
      // 固定为该财年首期、关闭锚点噪声，仅对比同一种子下有/无锚点的效果。
      // 不断言与系统时钟耦合的预测年月，也不重写生产预测公式。
      VB_YEAR = anchor.fy - 1
      VB_MON = 10
      FY_ANCHOR_SIGMA = 0
      const weight = FY_ANCHOR_WEIGHT
      FY_ANCHOR_WEIGHT = 0
      seedRng(42)
      const raw = simulate(currentParams)
      FY_ANCHOR_WEIGHT = weight
      seedRng(42)
      const anchored = simulate(currentParams)
      const september = path => path.find(point => {
        const date = new Date(point.x)
        return date.getUTCFullYear() === anchor.fy && date.getUTCMonth() === 8
      }).y
      return { enabled, anchor: anchor.y, october: october.y, raw: september(raw), anchored: september(anchored) }
    })
    expect(result.enabled).toBe(true)
    expect(result.anchor).not.toBeNull()
    expect(result.anchor).toBe(result.october)
    expect(Math.abs(result.anchored - result.anchor)).toBeLessThan(Math.abs(result.raw - result.anchor))
  })
}

test('bundled service worker caches the real subpath and serves it offline', async ({ page, context }) => {
  await openProfile(page)
  // 页面当前不自动注册；此用例独立验证分发的 worker 本身及其子路径作用域。
  const registration = await page.evaluate(async () => {
    await navigator.serviceWorker.register('./sw.js')
    const ready = await navigator.serviceWorker.ready
    return { scope: new URL(ready.scope).pathname, script: new URL(ready.active.scriptURL).pathname }
  })
  expect(registration).toEqual({ scope: '/site/', script: '/site/sw.js' })
  await page.reload()
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
  expect(await page.evaluate(() => typeof window.gsap)).toBe('object')
  const onlinePrediction = await page.locator('#ab-status').textContent()
  await context.setOffline(true)
  await page.reload()
  await expect(page.locator('#ab-status')).toHaveText(onlinePrediction)
  expect(await page.evaluate(() => typeof window.gsap)).toBe('object')
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="recent"]').click()
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
})

test('single HTML artifact renders from disk with no external requests', async ({ page, context }) => {
  const requests = []
  page.on('request', request => {
    if (/^https?:/.test(request.url())) requests.push(request.url())
  })
  await context.setOffline(true)
  await openProfile(page, 'EB-1A', 'CN', pathToFileURL(resolve('dist/EB1A.html')).href)
  await expect(page.locator('.footer')).toContainText('离线版')
  await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="recent"]').click()
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
  await page.reload()
  await expect(page.locator('#ab-status .ab-pred')).toHaveCount(2)
  expect(requests).toEqual([])
})
