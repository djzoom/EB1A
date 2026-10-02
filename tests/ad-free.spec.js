const { test, expect } = require('@playwright/test')
const { readFileSync, readdirSync } = require('node:fs')
const { resolve, join } = require('node:path')
const { pathToFileURL } = require('node:url')

// 同时守住在线包与离线包，避免只移除可见入口却保留广告模块或域名。
const forbidden = /bracketboss2026|adsterra|GCSPONSOR|GCSponsor|sponsor-link|sponsor\.open|gc_sponsor/i

test('published text artifacts contain no advertising integration or personal domain', () => {
  const root = resolve('dist/site')
  const files = readdirSync(root, { recursive: true })
    .filter(name => /\.(?:html|js|css|json)$/.test(name))
    .map(name => join(root, name))
  files.push(resolve('dist/EB1A.html'))
  expect(files.length).toBeGreaterThan(5)
  for (const file of files) expect(readFileSync(file, 'utf8'), file).not.toMatch(forbidden)
})

for (const offline of [false, true]) {
  test(`${offline ? 'offline' : 'online'} forecast has no ads or third-party requests`, async ({ page, context }) => {
    const externalRequests = []
    const errors = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (/^https?:$/.test(url.protocol) && (offline || url.origin !== 'http://127.0.0.1:4173')) {
        externalRequests.push(url.href)
      }
    })
    page.on('pageerror', error => errors.push(error.message))
    if (offline) await context.setOffline(true)
    const url = offline ? pathToFileURL(resolve('dist/EB1A.html')).href : './'
    await page.goto(url + '#share=1&category=EB-1A&country=CN&pd=2026-01-15&lang=zh-CN')
    await expect(page.locator('#hero-value')).not.toHaveText('--')
    for (const mode of ['wait', 'trend']) {
      await page.locator(`#mode-${mode}`).click()
      await expect(page.locator('#chart [data-series="forecast-A-p50"]')).toBeAttached()
      await expect(page.locator('#chart [data-series="forecast-B-p50"]')).toBeAttached()
    }
    const attribution = page.locator('.footer [data-i18n-html="footer.attribution"]')
    await expect(attribution).toHaveText('Fork 自 djzoom/EB1A')
    await expect(attribution.locator('a')).toHaveCount(1)
    await expect(attribution.locator('a'))
      .toHaveAttribute('href', 'https://github.com/djzoom/EB1A')
    await expect(page.locator('iframe, #sponsor-link, [data-sponsor]')).toHaveCount(0)
    expect(await page.evaluate(() => typeof window.GCSponsor)).toBe('undefined')
    expect(externalRequests).toEqual([])
    expect(errors).toEqual([])
  })
}
