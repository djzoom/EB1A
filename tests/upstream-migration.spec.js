const { test, expect } = require('@playwright/test')

async function openProfile(page) {
  await page.addInitScript(() => {
    localStorage.setItem('eb1a_user_profile', JSON.stringify({
      pd: Date.UTC(2026, 0, 15), category: 'EB-2', country: 'IN',
      path: 'AOS', family: 0, chartType: 'A'
    }))
  })
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#ab-status .ab-chip')).toHaveCount(2)
}

test('upstream cache migration serves the current snapshot without deleting unrelated caches', async ({ page, context }) => {
  await openProfile(page)
  const onlinePrediction = await page.locator('#ab-status').textContent()
  const seeded = await page.evaluate(async () => {
    const base = new URL('./', location.href)
    const prefix = 'gctime-' + base.pathname + '-'
    const staleName = prefix + 'obsolete-build'
    const manifest = await (await fetch('manifest.json')).json()
    const staleHTML = '<!doctype html><title>Old upstream</title><p id="stale-upstream">Old upstream snapshot</p>'
    const script = [...document.scripts].find(element => /\/assets\/ui\./.test(element.src)).src
    const style = document.querySelector('link[rel="stylesheet"]').href
    // 按创建顺序放入旧上游缓存；全局 caches.match 会先命中它。
    for (const name of ['eb1a-v3', 'eb1a-v4', 'other-project-offline', staleName]) {
      const cache = await caches.open(name)
      await cache.put(base.href, new Response(staleHTML, { headers: { 'Content-Type': 'text/html' } }))
      await cache.put(new URL('index.html', base), new Response(staleHTML, { headers: { 'Content-Type': 'text/html' } }))
      await cache.put(new URL('manifest.json', base), new Response('{"name":"old-manifest"}'))
      await cache.put(script, new Response('window.upstreamStaleUi = true', { headers: { 'Content-Type': 'text/javascript' } }))
      await cache.put(style, new Response('#gc-root { display: none }', { headers: { 'Content-Type': 'text/css' } }))
    }
    const otherURL = new URL('/another-project/keep.txt', base).href
    await (await caches.open('other-project-offline')).put(otherURL, new Response('keep-other-project'))
    await navigator.serviceWorker.register('./sw.js')
    await navigator.serviceWorker.ready
    return { prefix, staleName, manifestName: manifest.name, otherURL }
  })
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
  await expect.poll(() => page.evaluate(async name => (await caches.keys()).includes(name), seeded.staleName)).toBe(false)

  await context.setOffline(true)
  await page.reload()
  await expect(page.locator('#gc-root')).toHaveAttribute('data-ui', 'heroui-pro')
  await expect(page.locator('#ab-status')).toHaveText(onlinePrediction)
  await expect(page.locator('#stale-upstream')).toHaveCount(0)
  expect(await page.evaluate(() => window.upstreamStaleUi)).toBeUndefined()
  expect(await page.evaluate(async () => (await (await fetch('manifest.json')).json()).name)).toBe(seeded.manifestName)
  const retained = await page.evaluate(async ({ prefix, otherURL }) => {
    const names = await caches.keys()
    return {
      names,
      snapshots: names.filter(name => name.startsWith(prefix)).length,
      otherText: await (await (await caches.open('other-project-offline')).match(otherURL)).text()
    }
  }, seeded)
  expect(retained.names).toEqual(expect.arrayContaining(['eb1a-v3', 'eb1a-v4', 'other-project-offline']))
  expect(retained.snapshots).toBe(1)
  expect(retained.otherText).toBe('keep-other-project')
})

test('unavailable A and B cutoffs reuse their last dated history, not Current markers', async ({ page }) => {
  await openProfile(page)
  const values = await page.evaluate(() => {
    CUTOFF_DATA['EB-2'].IN = { A: 'unavailable', B: 'unavailable' }
    const expected = { A: '2013-11-01', B: '2015-01-15' }
    for (const table of ['A', 'B']) {
      const key = 'EB-2|IN|' + table
      HIST_DATA[key] = [
        ['2026-07-15', '2010-01-01'],
        ['2026-08-15', expected[table]],
        ['2026-09-15', 'C'],
        ['2026-10-15', 'U']
      ]
      delete _histCache[key]
    }
    return Object.fromEntries(['A', 'B'].map(table => [table,
      new Date(getCutoffData('EB-2', 'IN', table)).toISOString().slice(0, 10)
    ]))
  })
  expect(values).toEqual({ A: '2013-11-01', B: '2015-01-15' })
})
