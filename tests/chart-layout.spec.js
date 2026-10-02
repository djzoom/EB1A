const { test: base, expect } = require('@playwright/test')

const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors, '图表布局交互不应产生页面异常').toEqual([])
  }
})

async function openChart(page, width) {
  await page.setViewportSize({ width, height: 1000 })
  await page.addInitScript(() => {
    localStorage.setItem('eb1a_user_profile', JSON.stringify({
      pd: Date.UTC(2024, 0, 15), category: 'EB-3', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
    }))
  })
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#chart')).toBeVisible()
  await expect(page.locator('#chart path').first()).toBeAttached()
}

async function expectMatchingCanvas(page) {
  await expect.poll(() => page.locator('#chart').evaluate(svg => {
    const rect = svg.getBoundingClientRect()
    return Math.max(Math.abs(svg.viewBox.baseVal.width - rect.width), Math.abs(svg.viewBox.baseVal.height - rect.height))
  })).toBeLessThan(1)
}

for (const width of [375, 768, 1440, 1920]) {
  test(`chart fills its ${width}px workspace without shrinking its labels`, async ({ page }) => {
    await openChart(page, width)
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart [data-series="forecast-A-p50"]')).toBeAttached()
      await expect(page.locator('#chart [data-series="forecast-B-p50"]')).toBeAttached()
      await expectMatchingCanvas(page)
      const geometry = await page.locator('#chart').evaluate(svg => {
        const rect = svg.getBoundingClientRect()
        const matrix = svg.getScreenCTM()
        const plot = svg.querySelector('#plot-clip rect')
        const plotEnd = svg.createSVGPoint()
        plotEnd.x = Number(plot.getAttribute('x')) + Number(plot.getAttribute('width'))
        const labels = [...svg.querySelectorAll('text')]
        const axis = labels.filter(label => Math.abs(Number(label.getAttribute('y')) - (chartBounds.PAD.top + chartBounds.PH + 16)) < 1)
          .map(label => { const box = label.getBoundingClientRect(); return { left: box.left, right: box.right } })
        return {
          width: rect.width, height: rect.height,
          remaining: rect.right - plotEnd.matrixTransform(matrix).x,
          fonts: labels.map(label => parseFloat(getComputedStyle(label).fontSize) * matrix.a),
          axis,
          scrollWidth: document.documentElement.scrollWidth
        }
      })
      expect(geometry.height).toBe(width <= 767 ? 280 : 340)
      if (width >= 1440) expect(geometry.width).toBeGreaterThan(700)
      expect(geometry.remaining).toBeLessThan(35)
      expect(geometry.scrollWidth).toBeLessThanOrEqual(width)
      expect(Math.min(...geometry.fonts)).toBeGreaterThanOrEqual(10.99)
      expect(geometry.axis.length).toBeGreaterThanOrEqual(2)
      for (let index = 1; index < geometry.axis.length; index++) {
        expect(geometry.axis[index].left - geometry.axis[index - 1].right).toBeGreaterThanOrEqual(8)
      }
    }
  })
}

test('resizing only redraws layout, preserving forecasts and skipping animations', async ({ page }) => {
  await openChart(page, 1440)
  await expectMatchingCanvas(page)
  await page.evaluate(() => {
    window.chartTestState = {
      predictions: JSON.stringify(lastPercentiles), crossings: JSON.stringify([crossingsByPct, crossingsByPctB]),
      cloud: lastCloudPaths, rng: _rngState, simulations: 0, animations: 0, redraws: 0
    }
    const simulateOriginal = monteCarlo
    const animateOriginal = animateChart
    const redrawOriginal = redrawChart
    window.monteCarlo = function () { chartTestState.simulations++; return simulateOriginal.apply(this, arguments) }
    window.animateChart = function () { chartTestState.animations++; return animateOriginal.apply(this, arguments) }
    window.redrawChart = function () { chartTestState.redraws++; return redrawOriginal.apply(this, arguments) }
  })
  for (const width of [768, 375, 1920]) {
    await page.setViewportSize({ width, height: 1000 })
    await expectMatchingCanvas(page)
  }
  const state = await page.evaluate(() => ({
    samePredictions: chartTestState.predictions === JSON.stringify(lastPercentiles),
    sameCrossings: chartTestState.crossings === JSON.stringify([crossingsByPct, crossingsByPctB]),
    sameCloud: chartTestState.cloud === lastCloudPaths,
    sameRng: chartTestState.rng === _rngState,
    simulations: chartTestState.simulations, animations: chartTestState.animations, redraws: chartTestState.redraws
  }))
  expect(state).toMatchObject({ samePredictions: true, sameCrossings: true, sameCloud: true, sameRng: true, simulations: 0, animations: 0 })
  expect(state.redraws).toBeGreaterThan(0)
  await page.setViewportSize({ width: 1920, height: 900 })
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  expect(await page.evaluate(() => chartTestState.redraws)).toBe(state.redraws)

  await page.locator('#pe-cat').selectOption('EB-5-Rural')
  await page.locator('#pe-save').click()
  await expect(page.locator('.chart-widget')).toBeHidden()
  const hiddenChart = await page.locator('#chart').innerHTML()
  const beforeHiddenResize = await page.evaluate(() => chartTestState.redraws)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  expect(await page.locator('#chart').innerHTML()).toBe(hiddenChart)
  expect(await page.evaluate(() => chartTestState.redraws)).toBe(beforeHiddenResize)
  await page.locator('#pe-cat').selectOption('EB-3')
  await page.locator('#pe-save').click()
  await expect(page.locator('.chart-widget')).toBeVisible()
  await expectMatchingCanvas(page)
})

test('equal-width charts resize their canvas across the mobile height breakpoint', async ({ page }) => {
  await openChart(page, 600)
  await expectMatchingCanvas(page)
  const initialWidth = (await page.locator('#chart').boundingBox()).width
  const predictions = await page.evaluate(() => {
    window.chartBreakpointPaths = lastPercentiles
    return JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB, _rngState])
  })
  for (const width of [888, 600]) {
    await page.setViewportSize({ width, height: 1000 })
    await expectMatchingCanvas(page)
    const canvas = await page.locator('#chart').boundingBox()
    expect(canvas.width).toBeCloseTo(initialWidth, 1)
    expect(canvas.height).toBe(width === 600 ? 280 : 340)
    expect(await page.evaluate(() => chartBreakpointPaths === lastPercentiles)).toBe(true)
    expect(await page.evaluate(() => JSON.stringify([lastPercentiles, crossingsByPct, crossingsByPctB, _rngState]))).toBe(predictions)
  }
})

for (const mode of ['trend', 'wait']) {
  test(`mobile ${mode} tooltip follows the plotted point after resizing`, async ({ page }) => {
    await openChart(page, 1440)
    await page.locator(`#mode-${mode}`).click()
    await page.setViewportSize({ width: 375, height: 1000 })
    await expectMatchingCanvas(page)
    await page.locator('#chart').scrollIntoViewIfNeeded()
    const target = await page.locator('#chart').evaluate(svg => {
      const bounds = chartBounds
      const visible = lastSnapData.tables.A.p50.filter(point => point.x > bounds.xMin && point.x < bounds.xMax && point.y > bounds.yMin && point.y < bounds.yMax)
      const point = visible[Math.floor(visible.length * .7)]
      const coords = svg.createSVGPoint()
      coords.x = bounds.PAD.left + (point.x - bounds.xMin) / (bounds.xMax - bounds.xMin) * bounds.PW
      coords.y = bounds.PAD.top + (1 - (point.y - bounds.yMin) / (bounds.yMax - bounds.yMin)) * bounds.PH
      const screen = coords.matrixTransform(svg.getScreenCTM())
      // 原生鼠标按整数像素定位；窄屏的一像素可能覆盖数天，应检验该像素最近的共同采样点。
      const mouse = svg.createSVGPoint()
      mouse.x = Math.round(screen.x)
      mouse.y = Math.round(screen.y)
      const local = mouse.matrixTransform(svg.getScreenCTM().inverse())
      const dataX = bounds.xMin + (local.x - bounds.PAD.left) / bounds.PW * (bounds.xMax - bounds.xMin)
      const timeline = lastSnapData.timeline.filter(item => item.x >= bounds.xMin && item.x <= bounds.xMax)
      const snap = timeline.reduce((best, item) => Math.abs(item.x - dataX) < Math.abs(best.x - dataX) ? item : best)
      coords.x = bounds.PAD.left + (snap.x - bounds.xMin) / (bounds.xMax - bounds.xMin) * bounds.PW
      return { x: mouse.x, y: mouse.y, dotX: coords.matrixTransform(svg.getScreenCTM()).x, date: new Date(snap.x).toISOString().slice(0, 10) }
    })
    await page.mouse.move(target.x, target.y)
    const tooltip = page.locator('#chart-tooltip')
    await expect(tooltip).toBeVisible()
    await expect(tooltip.locator('.tt-hdr')).toContainText(target.date)
    for (const table of ['A', 'B']) await expect(tooltip.locator(`section[data-table="${table}"]`)).toBeVisible()
    const dot = await page.locator('#chart > circle[data-hover-table="A"]').boundingBox()
    expect(Math.abs(dot.x + dot.width / 2 - target.dotX)).toBeLessThan(1)
    const tip = await tooltip.boundingBox()
    const box = await page.locator('.chart-box').boundingBox()
    expect(tip.x).toBeGreaterThanOrEqual(box.x)
    expect(tip.x + tip.width).toBeLessThanOrEqual(box.x + box.width + 1)
    expect(tip.y).toBeGreaterThanOrEqual(box.y)
    expect(tip.y + tip.height).toBeLessThanOrEqual(box.y + box.height + 1)
  })
}
