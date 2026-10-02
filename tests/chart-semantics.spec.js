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
      ? lastSnapData.p50.slice(0, lastSnapData.predStart)
      : lastSnapData.p50.slice(lastSnapData.predStart + (chartMode === 'trend' ? 1 : 0))
    const candidates = series.filter(point => point.x > bounds.xMin && point.x < bounds.xMax && point.y > bounds.yMin && point.y < bounds.yMax)
    const point = month ? candidates.find(point => new Date(point.x).toISOString().slice(0, 7) === month)
      : candidates[Math.floor(candidates.length / 2)]
    if (!point) throw new Error('测试需要当前显示范围内的图表数据点')
    const coords = svg.createSVGPoint()
    coords.x = bounds.PAD.left + (point.x - bounds.xMin) / (bounds.xMax - bounds.xMin) * bounds.PW
    coords.y = bounds.PAD.top + (1 - (point.y - bounds.yMin) / (bounds.yMax - bounds.yMin)) * bounds.PH
    const screen = coords.matrixTransform(svg.getScreenCTM())
    return { x: screen.x, y: screen.y, date: new Date(point.x).toISOString().slice(0, 10) }
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
      for (const table of ['A', 'B']) {
        await page.locator('#ab-status .ab-chip').nth(table === 'A' ? 0 : 1).click()
        await hoverPoint(page, { month: record.month })
        for (const series of ['A', 'B']) {
          const row = page.locator(`#chart-tooltip [data-table="${series}"]`)
          await expect(row).toContainText(`表${series}`)
          await expect(row.locator('.tt-sval')).toHaveText(record[series])
        }
        await expect(page.locator('#chart-tooltip')).not.toContainText('中位')
      }
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

for (const table of ['A', 'B']) {
  test(`table ${table} predictions and legends keep their identity in both chart modes`, async ({ page }) => {
    await openChart(page, table)
    const selectedLabel = table === 'A' ? '表A裁定' : '表B递交'
    const otherTable = table === 'A' ? 'B' : 'A'
    const predictions = await page.evaluate(() => JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB]))
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart-description')).toContainText(selectedLabel)
      await expect(page.locator('#chart-description')).toContainText('实线历史，虚线预测')
      const styles = await page.evaluate(table => {
        const history = document.querySelector(`#chart [data-series="history-${table}"]`)
        const forecast = document.querySelector('#chart [data-series="forecast-p50"]')
        const pd = document.querySelector('#chart [data-series="pd"]')
        const historicalLegend = document.querySelector(`#chart-legend [data-series="history-${table}"] i`)
        const forecastLegend = document.querySelector('#chart-legend [data-series="forecast-p50"] i')
        const pdLegend = document.querySelector('#chart-legend [data-series="pd"] i')
        return {
          history: getComputedStyle(history).stroke, forecast: getComputedStyle(forecast).stroke,
          historyLegend: getComputedStyle(historicalLegend).backgroundColor, forecastLegend: getComputedStyle(forecastLegend).borderTopColor,
          historyDash: getComputedStyle(history).strokeDasharray, forecastDash: getComputedStyle(forecast).strokeDasharray,
          pd: getComputedStyle(pd).stroke, pdLegend: getComputedStyle(pdLegend).borderTopColor,
          edgeColors: [...document.querySelectorAll('#chart [data-series^="forecast-"], #chart .mc-line')].map(path => getComputedStyle(path).stroke)
        }
      }, table)
      expect(styles.history).toBe(styles.forecast)
      expect(styles.history).toBe(styles.historyLegend)
      expect(styles.forecast).toBe(styles.forecastLegend)
      expect(styles.historyDash).toBe('none')
      expect(styles.forecastDash).not.toBe('none')
      expect(styles.pd).toBe(styles.pdLegend)
      expect(styles.pd).not.toBe(styles.forecast)
      expect(styles.edgeColors.every(color => color === styles.forecast)).toBe(true)

      if (mode === 'wait') {
        await hoverPoint(page)
        await expect(page.locator('#chart-tooltip')).toContainText(selectedLabel)
        await expect(page.locator('#chart-tooltip')).toContainText('历史等待')
        await expect(page.locator('#chart-tooltip')).not.toContainText('中位')
      }
      await hoverPoint(page, { region: 'forecast' })
      await expect(page.locator('#chart-tooltip .tt-hdr')).toContainText(selectedLabel)
      await expect(page.locator('#chart-tooltip .tt-hdr')).toContainText(mode === 'wait' ? '等待预测' : '预测')
      await expect(page.locator('#chart-tooltip .tt-sname')).toHaveText(['乐观', '中位', '保守'])
      await expect(page.locator('#chart-tooltip')).toContainText('另一表请切换查看')
      await expect(page.locator('#chart-tooltip')).not.toContainText(`表${otherTable}`)
    }
    await page.locator('#ab-status .ab-chip').nth(table === 'A' ? 1 : 0).click()
    await expect(page.locator('#chart-legend [data-series="forecast-p50"]')).toContainText(`表${otherTable}`)
    expect(await page.evaluate(() => JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB]))).toBe(predictions)
  })
}
