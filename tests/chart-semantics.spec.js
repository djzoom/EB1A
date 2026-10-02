const { test: base, expect } = require('@playwright/test')

const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors).toEqual([])
  }
})

async function openChart(page, table = 'A') {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(table => {
    localStorage.setItem('eb1a_user_profile', JSON.stringify({
      pd: Date.UTC(2024, 0, 15), category: 'EB-3', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
    }))
    localStorage.setItem('eb1a_ab_view', table)
  }, table)
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#chart')).toBeVisible()
}

async function hoverPoint(page, { region = 'history', month = null } = {}) {
  await page.locator('#chart').scrollIntoViewIfNeeded()
  const target = await page.locator('#chart').evaluate((svg, { region, month }) => {
    const bounds = chartBounds
    const series = region === 'history'
      ? lastSnapData.tables.A.history
      : lastSnapData.tables.A.p50
    const candidates = series.filter(point => point.x > bounds.xMin && point.x < bounds.xMax && point.y > bounds.yMin && point.y < bounds.yMax &&
      (region !== 'forecast' || chartMode !== 'wait' || point.x > Math.max(lastSnapData.tables.A.cutoff, lastSnapData.tables.B.cutoff)))
    const point = month ? candidates.find(point => new Date(point.x).toISOString().slice(0, 7) === month)
      : candidates[Math.floor(candidates.length / 2)]
    if (!point) throw new Error('测试需要当前显示范围内的图表数据点')
    const coords = svg.createSVGPoint()
    coords.x = bounds.PAD.left + (point.x - bounds.xMin) / (bounds.xMax - bounds.xMin) * bounds.PW
    coords.y = bounds.PAD.top + (1 - (point.y - bounds.yMin) / (bounds.yMax - bounds.yMin)) * bounds.PH
    const screen = coords.matrixTransform(svg.getScreenCTM())
    const mouse = svg.createSVGPoint()
    mouse.x = Math.round(screen.x)
    mouse.y = Math.round(screen.y)
    const local = mouse.matrixTransform(svg.getScreenCTM().inverse())
    const dataX = bounds.xMin + (local.x - bounds.PAD.left) / bounds.PW * (bounds.xMax - bounds.xMin)
    const timeline = lastSnapData.timeline.filter(item => item.x >= bounds.xMin && item.x <= bounds.xMax)
    const snap = timeline.reduce((best, item) => Math.abs(item.x - dataX) < Math.abs(best.x - dataX) ? item : best)
    return { x: mouse.x, y: mouse.y, date: new Date(snap.x).toISOString().slice(0, 10) }
  }, { region, month })
  await page.mouse.move(target.x, target.y)
  await expect(page.locator('#chart-tooltip')).toBeVisible()
  await expect(page.locator('#chart-tooltip .tt-hdr')).toContainText(target.date)
  return target
}

for (const timezoneId of ['UTC', 'America/Los_Angeles']) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId })
    test('historical tooltip pairs the same bulletin month and preserves the UTC cutoff day', async ({ page }) => {
      await openChart(page)
      const record = await page.evaluate(() => {
        const key = timestamp => new Date(timestamp).toISOString().slice(0, 7)
        const point = histA().find(point => {
          const other = histB().find(other => key(other.x) === key(point.x))
          return point.x > chartBounds.xMin && point.x < chartBounds.xMax &&
            point.y > chartBounds.yMin && point.y < chartBounds.yMax &&
            new Date(point.y).getUTCDate() === 1 && other && other.y > chartBounds.yMin && other.y < chartBounds.yMax
        })
        const other = histB().find(other => key(other.x) === key(point.x))
        return { month: key(point.x), A: new Date(point.y).toISOString().slice(0, 10), B: new Date(other.y).toISOString().slice(0, 10) }
      })
      await hoverPoint(page, { month: record.month })
      for (const series of ['A', 'B']) {
        const row = page.locator(`#chart-tooltip .tt-series[data-table="${series}"]`)
        await expect(row).toContainText(`表${series}`)
        await expect(row.locator('.tt-sval')).toHaveText(record[series])
      }
      await expect(page.locator('#chart-tooltip')).not.toContainText('中位')
    })
  })
}

test('missing historical B data is not borrowed from a neighboring bulletin', async ({ page }) => {
  await openChart(page)
  const target = await hoverPoint(page)
  const month = target.date.slice(0, 7)
  await page.evaluate(month => {
    const original = histB
    window.histB = () => original().filter(point => new Date(point.x).toISOString().slice(0, 7) !== month)
    redrawChart(true)
  }, month)
  await hoverPoint(page, { month })
  await expect(page.locator('#chart-tooltip [data-table="B"] .tt-sval')).toHaveText('本月无数据')
  await expect(page.locator('#chart-tooltip [data-table="A"] .tt-sval')).not.toHaveText('本月无数据')
})

for (const legacyView of ['A', 'B']) {
  test(`both table predictions and legends keep their identity with legacy ${legacyView} preference`, async ({ page }) => {
    await openChart(page, legacyView)
    const predictions = await page.evaluate(() => JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB]))
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart-description')).toContainText('表 A')
      await expect(page.locator('#chart-description')).toContainText('表 B')
      await expect(page.locator('#chart-description')).toContainText('实线历史，虚线预测')
      const styles = await page.evaluate(() => ['A', 'B'].map(table => {
        const history = document.querySelector(`#chart [data-series="history-${table}"]`)
        const forecast = document.querySelector(`#chart [data-series="forecast-${table}-p50"]`)
        const pd = document.querySelector('#chart [data-series="pd"]')
        const historicalLegend = document.querySelector(`#chart-legend [data-series="history-${table}"] i`)
        const forecastLegend = document.querySelector(`#chart-legend [data-series="forecast-${table}-p50"] i`)
        const pdLegend = document.querySelector('#chart-legend [data-series="pd"] i')
        return {
          history: getComputedStyle(history).stroke, forecast: getComputedStyle(forecast).stroke,
          historyLegend: getComputedStyle(historicalLegend).backgroundColor, forecastLegend: getComputedStyle(forecastLegend).borderTopColor,
          historyDash: getComputedStyle(history).strokeDasharray, forecastDash: getComputedStyle(forecast).strokeDasharray,
          pd: getComputedStyle(pd).stroke, pdLegend: getComputedStyle(pdLegend).borderTopColor,
          edgeColors: [...document.querySelectorAll(`#chart [data-series^="forecast-${table}-"]`)].map(path => getComputedStyle(path).stroke)
        }
      }))
      for (const style of styles) {
        expect(style.history).toBe(style.forecast)
        expect(style.history).toBe(style.historyLegend)
        expect(style.forecast).toBe(style.forecastLegend)
        expect(style.historyDash).toBe('none')
        expect(style.forecastDash).not.toBe('none')
        expect(style.pd).toBe(style.pdLegend)
        expect(style.pd).not.toBe(style.forecast)
        expect(style.edgeColors.every(color => color === style.forecast)).toBe(true)
      }
      expect(styles[0].forecast).not.toBe(styles[1].forecast)
      await hoverPoint(page, { region: 'forecast' })
      for (const table of ['A', 'B']) {
        const section = page.locator(`#chart-tooltip section[data-table="${table}"]`)
        await expect(section.locator('.tt-label')).toContainText(`表${table}`)
        await expect(section.locator('.tt-sname')).toHaveText(['乐观', '中位', '保守'])
        await expect(section.locator('[data-percentile]')).toHaveCount(3)
      }
      await expect(page.locator('#chart-tooltip')).not.toContainText('另一表请切换查看')
    }
    expect(await page.evaluate(() => JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB]))).toBe(predictions)
  })
}
