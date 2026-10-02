const { test, expect } = require('@playwright/test')
const { createHash } = require('node:crypto')

test('published UI URLs match their contents and the worker precache', async ({ page, request }) => {
  await page.goto('./')
  const urls = await page.evaluate(() => ({
    script: [...document.scripts].find(el => /\/assets\/ui\./.test(el.src)).src,
    style: document.querySelector('link[rel="stylesheet"]').href
  }))
  const worker = await request.get('sw.js')
  expect(worker.ok()).toBeTruthy()
  const workerText = await worker.text()
  for (const [type, url] of Object.entries(urls)) {
    const extension = type === 'script' ? 'js' : 'css'
    expect(new URL(url).pathname).toMatch(new RegExp(`/assets/ui\\.[a-f0-9]{16}\\.${extension}$`))
    const asset = await request.get(url)
    expect(asset.ok()).toBeTruthy()
    const hash = createHash('sha256').update(await asset.body()).digest('hex').slice(0, 16)
    expect(url).toContain(`ui.${hash}.${extension}`)
    expect(workerText).toContain(`'./assets/ui.${hash}.${extension}'`)
  }
})

test('new pages do not consume stale unversioned UI resources', async ({ page }) => {
  const staleRequests = []
  await page.route('**/assets/ui.js', route => {
    staleRequests.push(route.request().url())
    return route.fulfill({ contentType: 'text/javascript', body: 'window.staleUiLoaded = true' })
  })
  await page.route('**/assets/ui.css', route => {
    staleRequests.push(route.request().url())
    return route.fulfill({ contentType: 'text/css', body: '.forecast-sheet { display: none !important }' })
  })
  await page.goto('./')
  await expect(page.locator('#gc-root')).toHaveAttribute('data-ui', 'heroui-pro')
  await expect(page.locator('.forecast-sheet')).toBeVisible()
  expect(await page.evaluate(() => window.staleUiLoaded)).toBeUndefined()
  expect(staleRequests).toEqual([])
})
