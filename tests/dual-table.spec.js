const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')

const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors, '双表展示和提示不应产生页面异常').toEqual([])
  }
})

async function openChart(page, legacyView = 'B') {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(view => {
    localStorage.setItem('eb1a_user_profile', JSON.stringify({
      pd: Date.UTC(2026, 0, 15), category: 'EB-3', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
    }))
    localStorage.setItem('eb1a_ab_view', view)
  }, legacyView)
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#chart path').first()).toBeAttached()
}

async function hoverX(page, x) {
  await page.locator('#chart').scrollIntoViewIfNeeded()
  const screen = await page.locator('#chart').evaluate((svg, x) => {
    const point = svg.createSVGPoint()
    point.x = chartBounds.PAD.left + (x - chartBounds.xMin) / (chartBounds.xMax - chartBounds.xMin) * chartBounds.PW
    point.y = chartBounds.PAD.top + chartBounds.PH / 2
    const screen = point.matrixTransform(svg.getScreenCTM())
    const mouse = svg.createSVGPoint()
    mouse.x = Math.round(screen.x)
    mouse.y = Math.round(screen.y)
    const local = mouse.matrixTransform(svg.getScreenCTM().inverse())
    const dataX = chartBounds.xMin + (local.x - chartBounds.PAD.left) / chartBounds.PW * (chartBounds.xMax - chartBounds.xMin)
    const timeline = lastSnapData.timeline.filter(item => item.x >= chartBounds.xMin && item.x <= chartBounds.xMax)
    const snap = timeline.reduce((best, item) => Math.abs(item.x - dataX) < Math.abs(best.x - dataX) ? item : best)
    return { x: mouse.x, y: mouse.y, date: new Date(snap.x).toISOString().slice(0, 10) }
  }, x)
  await page.mouse.move(screen.x, screen.y)
  await expect(page.locator('#chart-tooltip')).toBeVisible()
  await expect(page.locator('#chart-tooltip .tt-hdr')).toContainText(screen.date)
  return screen
}

test('A and B results are static cards rather than mutually exclusive controls', async ({ page }) => {
  await openChart(page)
  await expect(page.locator('#ab-status .ab-chip[data-table]')).toHaveCount(2)
  await expect(page.locator('#ab-status button, #ab-status [role="tab"], #ab-status [role="tablist"]')).toHaveCount(0)
  await expect(page.locator('#ab-status [aria-selected], #ab-status .selected')).toHaveCount(0)
  for (const table of ['A', 'B']) await expect(page.locator(`#ab-status .ab-chip[data-table="${table}"] .ab-pred`)).toBeVisible()
})

for (const mode of ['trend', 'wait']) {
  test(`${mode} plots both tables despite a legacy saved B selection`, async ({ page }) => {
    await openChart(page)
    await page.locator(`#mode-${mode}`).click()
    for (const table of ['A', 'B']) {
      for (const series of [`history-${table}`, `forecast-${table}-p50`, `range-${table}`]) {
        await expect(page.locator(`#chart [data-series="${series}"]`).first()).toBeAttached()
      }
    }
    expect(await page.evaluate(() => Object.keys(lastSnapData.tables).sort())).toEqual(['A', 'B'])
  })
}

test('trend forecasts compare the same month even when B has missing or offset monthly samples', async ({ page }) => {
  await openChart(page)
  const sample = await page.evaluate(() => {
    const visible = lastSnapData.tables.A.p50.filter(point => point.x > TODAY && point.x < chartBounds.xMax && point.y < chartBounds.yMax)
    const point = visible[Math.floor(visible.length / 2)]
    const date = value => new Date(value).toISOString().slice(0, 10)
    const expected = {}
    for (const table of ['A', 'B']) {
      expected[table] = {}
      for (const percentile of ['p10', 'p50', 'p90']) {
        expected[table][percentile] = date(lastSnapData.tables[table][percentile].find(item => item.x === point.x).y)
      }
    }
    // B 少一条更早月份，不能用 A 的数组下标读取 B。
    for (const percentile of ['p10', 'p50', 'p90']) lastSnapData.tables.B[percentile].splice(1, 1)
    return { x: point.x, expected }
  })
  await hoverX(page, sample.x)
  for (const table of ['A', 'B']) {
    for (const percentile of ['p10', 'p50', 'p90']) {
      await expect(page.locator(`#chart-tooltip section[data-table="${table}"] [data-percentile="${percentile}"] .tt-sval`))
        .toHaveText(sample.expected[table][percentile])
    }
  }
  await page.evaluate(x => {
    for (const percentile of ['p10', 'p50', 'p90']) lastSnapData.tables.B[percentile] = lastSnapData.tables.B[percentile].filter(point => point.x !== x)
  }, sample.x)
  await page.mouse.move(0, 0)
  await hoverX(page, sample.x)
  const unavailable = await page.evaluate(() => i18n.text('chart.outsideRange'))
  await expect(page.locator('#chart-tooltip section[data-table="B"] .tt-sval')).toHaveText([unavailable, unavailable, unavailable])
  await expect(page.locator('#chart-tooltip section[data-table="A"] [data-percentile="p50"] .tt-sval')).toHaveText(sample.expected.A.p50)
  await expect(page.locator('#chart > circle[data-hover-table="B"]')).toHaveCount(0)
})

for (const forecastTable of ['A', 'B']) {
  test(`wait tooltip interpolates the common PD for forecast ${forecastTable} and the other table history independently`, async ({ page }) => {
    await openChart(page)
    await page.locator('#mode-wait').click()
    const fixture = await page.evaluate(forecastTable => {
      const x = Math.round((chartBounds.xMin + chartBounds.xMax) / 2)
      const step = Math.min((chartBounds.xMax - chartBounds.xMin) / 10, 60 * MS_PER_DAY)
      const points = entries => entries.map(([offset, y]) => ({ x: x + offset * step, y }))
      const forecast = {
        cutoff: x - step, history: points([[-3, 1], [-2, 3]]),
        p10: points([[-1, 2], [1, 4]]), p50: points([[-2, 4], [2, 8]]), p90: points([[-3, 9], [1, 13]])
      }
      const historical = { cutoff: x + step, history: points([[-1, 1], [1, 3]]), p10: [], p50: [], p90: [] }
      lastSnapData = { mode: 'wait', timeline: [{ x }], tables: forecastTable === 'A' ? { A: forecast, B: historical } : { A: historical, B: forecast } }
      chartBounds.yMin = 0
      chartBounds.yMax = 20
      return { x, forecast: [3, 6, 12].map(value => i18n.formatUnit(value, 'year')), history: i18n.formatUnit(2, 'year') }
    }, forecastTable)
    const otherTable = forecastTable === 'A' ? 'B' : 'A'
    const screen = await hoverX(page, fixture.x)
    await expect(page.locator(`#chart-tooltip section[data-table="${forecastTable}"] .tt-sval`)).toHaveText(fixture.forecast)
    const history = page.locator(`#chart-tooltip section[data-table="${otherTable}"]`)
    await expect(history.locator('.tt-sname')).toHaveText('历史等待')
    await expect(history.locator('.tt-sval')).toHaveText(fixture.history)
    await expect(history.locator('[data-percentile]')).toHaveCount(0)
    for (const table of ['A', 'B']) {
      const dot = await page.locator(`#chart > circle[data-hover-table="${table}"]`).boundingBox()
      expect(Math.abs(dot.x + dot.width / 2 - screen.x)).toBeLessThan(1)
    }
    // 超出任一独立数组范围，不能借相邻数组或跨历史/预测边界外推。
    const unavailable = await page.evaluate(({ forecastTable, otherTable, x }) => {
      lastSnapData.tables[forecastTable].p10 = [{ x: x + 1, y: 1 }, { x: x + 2, y: 2 }]
      lastSnapData.tables[otherTable].history = [{ x: x - 2, y: 1 }, { x: x - 1, y: 2 }]
      lastSnapData.tables[otherTable].p50 = [{ x: x - 1, y: 8 }, { x: x + 1, y: 10 }]
      return i18n.text('chart.outsideRange')
    }, { forecastTable, otherTable, x: fixture.x })
    await page.mouse.move(0, 0)
    await hoverX(page, fixture.x)
    await expect(page.locator(`#chart-tooltip section[data-table="${forecastTable}"] [data-percentile="p10"] .tt-sval`)).toHaveText(unavailable)
    await expect(page.locator(`#chart-tooltip section[data-table="${forecastTable}"] [data-percentile="p50"] .tt-sval`)).toHaveText(fixture.forecast[1])
    await expect(history.locator('.tt-sval')).toHaveText(unavailable)
    await expect(page.locator(`#chart > circle[data-hover-table="${otherTable}"]`)).toHaveCount(0)
  })
}

for (const [locale, width] of [['zh-CN', 375], ['de', 1440], ['ar', 375]]) {
  test(`${locale} dual-table tooltips stay readable inside the ${width}px chart in both modes`, async ({ page }) => {
    await page.addInitScript(locale => localStorage.setItem('gc_language', locale), locale)
    await openChart(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      const x = await page.evaluate(() => {
        const min = chartMode === 'wait' ? Math.max(lastSnapData.tables.A.cutoff, lastSnapData.tables.B.cutoff) : TODAY
        const points = lastSnapData.tables.A.p50.filter(point => point.x > min && point.x > chartBounds.xMin && point.x < chartBounds.xMax)
        return points[Math.floor(points.length / 2)].x
      })
      await hoverX(page, x)
      for (const table of ['A', 'B']) {
        const section = page.locator(`#chart-tooltip section[data-table="${table}"]`)
        await expect(section).toBeVisible()
        await expect(section.locator('[data-percentile]')).toHaveCount(3)
      }
      const tip = await page.locator('#chart-tooltip').boundingBox()
      const box = await page.locator('.chart-box').boundingBox()
      expect(tip.x).toBeGreaterThanOrEqual(box.x)
      expect(tip.x + tip.width).toBeLessThanOrEqual(box.x + box.width + 1)
      expect(tip.y).toBeGreaterThanOrEqual(box.y)
      expect(tip.y + tip.height).toBeLessThanOrEqual(box.y + box.height + 1)
      if (process.env.GCTIME_VISUAL_DIR) await page.locator('.chart-box').screenshot({ path: resolve(process.env.GCTIME_VISUAL_DIR, `${locale}-${width}-${mode}-tooltip.png`) })
    }
  })
}
