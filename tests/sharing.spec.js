const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')
const { pathToFileURL } = require('node:url')

const profileKey = 'eb1a_user_profile'
const savedProfile = {
  pd: Date.UTC(2026, 0, 15), category: 'EB-1A', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
}

const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    // 所有复制都截留在当前测试页面，不接触系统剪贴板。
    await page.addInitScript(() => {
      window.sharingCopies = []
      window.sharingCopyRejected = false
      window.sharingFallbackCalls = []
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async value => {
            window.sharingCopies.push(value)
            if (window.sharingCopyRejected) throw new DOMException('Clipboard denied', 'NotAllowedError')
          }
        }
      })
      document.execCommand = command => {
        window.sharingFallbackCalls.push(command)
        return false
      }
    })
    await use(page)
    expect(errors, '分享、编辑和重载不应产生页面异常').toEqual([])
  }
})

test.use({ locale: 'zh-CN' })

function shareHash(overrides = {}) {
  const values = new URLSearchParams({
    share: '1', category: 'EB-3', country: 'CN', pd: '2024-02-29', view: 'B',
    pace: 'model', percentile: 'p50', lang: 'zh-CN', ...overrides
  })
  return `#${values}`
}

async function seedSavedProfile(page) {
  await page.addInitScript(({ key, profile }) => {
    if (!localStorage.getItem(key)) {
      localStorage.setItem(key, JSON.stringify(profile))
      localStorage.setItem('eb1a_ab_view', 'A')
      localStorage.setItem('gc_pace_mode', 'model')
    }
  }, { key: profileKey, profile: savedProfile })
}

async function expectReady(page) {
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#hero-value')).not.toHaveText('--')
}

async function copyLink(page) {
  const before = await page.evaluate(() => sharingCopies.length)
  await page.locator('#share-btn').click()
  await expect.poll(() => page.evaluate(() => sharingCopies.length)).toBe(before + 1)
  return page.evaluate(() => sharingCopies.at(-1))
}

for (const view of ['A', 'B']) {
  test(`legacy view=${view} links show both tables and copied links omit the retired view field`, async ({ page }) => {
    await seedSavedProfile(page)
    await page.goto(`./${shareHash({ view, country: 'IN' })}`)
    await expectReady(page)
    await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
    for (const mode of ['trend', 'wait']) {
      await page.locator(`#mode-${mode}`).click()
      for (const table of ['A', 'B']) {
        await expect(page.locator(`#ab-status .ab-chip[data-table="${table}"]`)).toBeVisible()
        await expect(page.locator(`#chart [data-series="forecast-${table}-p50"]`)).toBeAttached()
      }
    }
    const hash = new URLSearchParams(new URL(await copyLink(page)).hash.slice(1))
    expect(hash.has('view')).toBe(false)
    expect(Object.fromEntries(['category', 'country', 'pd'].map(key => [key, hash.get(key)])))
      .toEqual({ category: 'EB-3', country: 'IN', pd: '2024-02-29' })
    expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), profileKey)).toEqual(savedProfile)
  })
}

for (const timezoneId of ['UTC', 'America/Los_Angeles', 'Asia/Shanghai']) {
  test.describe(`shared calendar dates in ${timezoneId}`, () => {
    test.use({ timezoneId })
    test('a fresh recipient sees the exact shared leap day without creating a saved profile', async ({ page }) => {
      await page.goto(`./${shareHash()}`)
      await expectReady(page)
      await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
      expect(await page.evaluate(() => {
        const date = new Date(profile.pd)
        return { category: profile.category, country: profile.country, date: [date.getFullYear(), date.getMonth() + 1, date.getDate()] }
      })).toEqual({ category: 'EB-3', country: 'CN', date: [2024, 2, 29] })
      await expect(page.locator('#chart [data-series="forecast-A-p50"]')).toBeAttached()
      await expect(page.locator('#chart [data-series="forecast-B-p50"]')).toBeAttached()
      expect(await page.evaluate(key => localStorage.getItem(key), profileKey)).toBeNull()
      const url = new URL(await copyLink(page))
      expect(new URLSearchParams(url.hash.slice(1)).get('pd')).toBe('2024-02-29')
    })
  })
}

test('the parser rejects invalid dates and identifiers and defaults an omitted country safely', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto('./')
  await expectReady(page)
  const results = await page.evaluate(() => {
    const parse = overrides => window.GCShare.parse('#' + new URLSearchParams({
      share: '1', category: 'EB-3', pd: '2024-02-29', ...overrides
    }), CATEGORIES.map(item => item.id), COUNTRIES.map(item => item.id))
    return {
      invalidDates: ['1989-12-31', '2100-01-01', '2023-02-29', '2024-02-31', '2024-13-01', '2024-2-01', '2024-01-01<script>'].map(pd => parse({ pd })),
      invalidCategory: parse({ category: '__proto__' }),
      invalidCountry: parse({ country: 'unknown' }),
      defaults: parse({})
    }
  })
  expect(results.invalidDates.every(result => result && result.invalid === true)).toBe(true)
  expect(results.invalidCategory).toEqual({ invalid: true })
  expect(results.invalidCountry).toEqual({ invalid: true })
  expect(results.defaults.profile.country).toBe('CN')
  expect(results.defaults).toMatchObject({ pace: 'model', percentile: 'p50' })
})

test('shared conditions override the display without overwriting the recipient profile or preferences', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto(`./${shareHash({ country: 'IN', pace: 'recent' })}`)
  await expectReady(page)
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
  await expect(page.locator('#shared-notice')).toBeVisible()
  expect(await page.evaluate(() => ({ category: profile.category, country: profile.country, pace: paceMode })))
    .toEqual({ category: 'EB-3', country: 'IN', pace: 'recent' })
  // 分享预览内切换也不能悄悄改掉接收者原有偏好。
  await expect(page.locator('#ab-status .ab-chip[data-table]')).toHaveCount(2)
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="model"]').click()
  await page.locator('[data-pace="recent"]').click()
  expect(await page.evaluate(key => ({ profile: JSON.parse(localStorage.getItem(key)), view: localStorage.getItem('eb1a_ab_view'), pace: localStorage.getItem('gc_pace_mode') }), profileKey))
    .toEqual({ profile: savedProfile, view: 'A', pace: 'model' })
})

test('same-document share navigation applies incoming conditions and language while back restores the saved profile', async ({ page }) => {
  await seedSavedProfile(page)
  await page.addInitScript(() => {
    if (!localStorage.getItem('gc_language')) localStorage.setItem('gc_language', 'ja')
  })
  await page.goto('./')
  await expectReady(page)
  await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
  await expect(page.locator('#pv-pd')).toHaveText('2026-01-15')
  const stored = await page.evaluate(key => ({
    profile: localStorage.getItem(key), view: localStorage.getItem('eb1a_ab_view'),
    pace: localStorage.getItem('gc_pace_mode'), language: localStorage.getItem('gc_language')
  }), profileKey)

  // 只改同一页面的 hash，测试用户粘贴第二条分享链接；不得手动 reload 掩盖问题。
  await page.goto('./#share=1&category=EB-3&country=IN&pd=2024-02-29&view=B&lang=fr')
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
  await expect(page.locator('#language-select')).toHaveValue('fr')
  await expect(page.locator('#shared-notice')).toBeVisible()
  expect(await page.evaluate(() => ({ category: profile.category, country: profile.country, pace: paceMode })))
    .toEqual({ category: 'EB-3', country: 'IN', pace: 'model' })
  await expect(page.locator('#ab-status .ab-chip[data-table]')).toHaveCount(2)
  expect(await page.evaluate(key => ({
    profile: localStorage.getItem(key), view: localStorage.getItem('eb1a_ab_view'),
    pace: localStorage.getItem('gc_pace_mode'), language: localStorage.getItem('gc_language')
  }), profileKey)).toEqual(stored)

  // 键盘跳转只移动焦点，不覆盖分享 hash，也不触发重载丢失预览。
  const incomingHash = new URL(page.url()).hash
  await page.evaluate(() => { window.sharingNavigationToken = 'preview-document' })
  await page.locator('.skip-link').focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#forecast-workspace')).toBeFocused()
  expect(new URL(page.url()).hash).toBe(incomingHash)
  expect(await page.evaluate(() => window.sharingNavigationToken)).toBe('preview-document')
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')

  await page.goBack()
  await expect(page.locator('#pv-pd')).toHaveText('2026-01-15')
  await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
  await expect(page.locator('#shared-notice')).toBeHidden()
  expect(new URL(page.url()).hash).toBe('')
  expect(await page.evaluate(() => ({ active: profile, pace: paceMode })))
    .toEqual({ active: savedProfile, pace: 'model' })
  expect(await page.evaluate(key => ({
    profile: localStorage.getItem(key), view: localStorage.getItem('eb1a_ab_view'),
    pace: localStorage.getItem('gc_pace_mode'), language: localStorage.getItem('gc_language')
  }), profileKey)).toEqual(stored)
})

test('explicitly saving edited shared conditions removes the snapshot and survives reload', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await seedSavedProfile(page)
  await page.goto(`./${shareHash()}`)
  await expectReady(page)
  await page.locator('#profile-toggle').click()
  await page.locator('#pe-cat').selectOption('EB-2')
  await page.locator('#pe-co').selectOption('IN')
  await page.locator('#pe-pd-y').fill('2025')
  await page.locator('#pe-pd-m').fill('03')
  await page.locator('#pe-pd-d').fill('07')
  await page.locator('#pe-save').click()
  expect(new URL(page.url()).hash).toBe('')
  await expect(page.locator('#shared-notice')).toBeHidden()
  await page.reload()
  await expectReady(page)
  await expect(page.locator('#pv-pd')).toHaveText('2025-03-07')
  await expect(page.locator('#pe-cat')).toHaveValue('EB-2')
  await expect(page.locator('#pe-co')).toHaveValue('IN')
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), profileKey))
    .toMatchObject({ pd: Date.UTC(2025, 2, 7), category: 'EB-2', country: 'IN', chartType: 'A' })
})

for (const [name, overrides] of [
  ['impossible calendar date', { pd: '2024-02-31' }],
  ['HTML in a category identifier', { category: '<img data-sharing-injected src=x onerror="window.sharingInjected=true">' }],
  ['malformed parameter JSON', { params: '{"familyMultiplier":' }]
]) {
  test(`an invalid shared ${name} preserves the existing profile and reports the fallback`, async ({ page }) => {
    await seedSavedProfile(page)
    await page.goto(`./${shareHash(overrides)}`)
    await expectReady(page)
    await expect(page.locator('#shared-notice')).toBeVisible()
    await expect(page.locator('#shared-notice')).toContainText('无效')
    await expect(page.locator('#pv-pd')).toHaveText('2026-01-15')
    expect(await page.evaluate(key => ({ active: profile, stored: JSON.parse(localStorage.getItem(key)), injected: Boolean(window.sharingInjected) }), profileKey))
      .toEqual({ active: savedProfile, stored: savedProfile, injected: false })
    await expect(page.locator('[data-sharing-injected]')).toHaveCount(0)
  })
}

for (const [name, params] of [
  ['out-of-bounds values', '{"spilloverROW":4200,"familyMultiplier":0}'],
  ['prototype and unknown keys', '{"spilloverROW":4200,"__proto__":{"sharingPolluted":true},"toString":1}'],
  ['non-finite values', '{"spilloverROW":1e309}']
]) {
  test(`shared parameters reject ${name} atomically and use the selected model defaults`, async ({ page }) => {
    await seedSavedProfile(page)
    await page.goto(`./${shareHash({ category: 'EB-1A', params })}`)
    await expectReady(page)
    await expect(page.locator('#shared-notice')).toContainText('参数无效')
    expect(await page.evaluate(key => ({
      defaults: JSON.stringify(currentParams) === JSON.stringify(activeModel().presets.realistic),
      finite: Object.values(currentParams).every(Number.isFinite),
      polluted: Boolean(({}).sharingPolluted), stored: JSON.parse(localStorage.getItem(key))
    }), profileKey)).toEqual({ defaults: true, finite: true, polluted: false, stored: savedProfile })
    await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
    expect(await page.locator('#chart').innerHTML()).not.toMatch(/NaN|Infinity/)
  })
}

test('a copied snapshot restores all model parameters, pace, percentile and supply without a single-table view', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto('./')
  await expectReady(page)
  await page.locator('[data-pct="p90"]').click()
  await page.locator('[data-tab="settings"]').click()
  await page.locator('[data-pace="recent"]').click()
  await page.locator('[data-sc="tight"]').click()
  await page.locator('#familyMultiplier').evaluate(input => {
    input.value = '2.4'
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect.poll(() => page.evaluate(() => currentParams.familyMultiplier)).toBe(2.4)
  const snapshot = await page.evaluate(() => ({
    params: { ...currentParams }, pace: paceMode, percentile: selectedPercentile,
    supply: supplyScenario, model: activeModel().key, chartType: profile.chartType
  }))
  const url = await copyLink(page)
  const fragment = new URLSearchParams(new URL(url).hash.slice(1))
  expect(JSON.parse(fragment.get('params'))).toEqual(snapshot.params)
  expect(fragment.has('view')).toBe(false)
  expect(fragment.get('pace')).toBe('recent')
  expect(fragment.get('percentile')).toBe('p90')
  expect(fragment.get('supply')).toBe('tight')
  // 应用在分享 hash 变化后自动重载；等待旧文档标记消失，避免旧界面造成误通过。
  await page.evaluate(() => { window.sharingNavigationToken = 'snapshot-document' })
  await page.goto(url)
  await page.waitForFunction(() => window.sharingNavigationToken === undefined)
  await expectReady(page)
  await expect(page.locator('#shared-notice')).toBeVisible()
  expect(await page.evaluate(() => ({
    params: { ...currentParams }, pace: paceMode, percentile: selectedPercentile,
    supply: supplyScenario, model: activeModel().key, chartType: profile.chartType
  }))).toEqual(snapshot)
  await expect(page.locator('#ab-status .ab-chip[data-table]')).toHaveCount(2)
  await expect(page.locator('[data-pct="p90"]')).toHaveClass(/selected/)
  await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
  await expect(page.locator('[data-sc="tight"]')).toHaveClass(/active/)
})

test('repeated copying keeps the current site subpath, removes unrelated URL data and preserves the button icon', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto('./?unrelated=do-not-share#unrelated-fragment')
  await expectReady(page)
  const current = new URL(page.url())
  for (let count = 0; count < 2; count++) {
    const copied = new URL(await copyLink(page))
    expect(copied.origin).toBe(current.origin)
    expect(copied.pathname).toBe(current.pathname)
    expect(copied.pathname).toContain('/site/')
    expect(copied.search).toBe('')
    expect(copied.href).not.toContain('unrelated')
    expect(new URLSearchParams(copied.hash.slice(1)).get('category')).toBe('EB-1A')
    await expect(page.locator('#action-status')).toContainText('已复制')
    await expect(page.locator('#share-url')).toBeHidden()
    await expect(page.locator('#share-btn svg')).toHaveCount(1)
  }
  expect(await page.evaluate(() => sharingFallbackCalls)).toEqual([])
  const rootLink = await page.evaluate(() => window.GCShare.build('https://example.com/?private=1#old', {
    category: 'EB-3', country: 'IN', pd: '2024-02-29', view: 'B', pace: 'model', percentile: 'p50'
  }))
  expect(new URL(rootLink).origin).toBe('https://example.com')
  expect(new URL(rootLink).pathname).toBe('/')
  expect(new URL(rootLink).search).toBe('')
})

test('clipboard rejection and a false legacy copy result expose a selected manual link without claiming success', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto('./')
  await expectReady(page)
  await page.evaluate(() => { sharingCopyRejected = true })
  const copied = await copyLink(page)
  const input = page.locator('#share-url')
  await expect(input).toBeVisible()
  await expect(input).toHaveValue(copied)
  await expect(input).toBeFocused()
  expect(await input.evaluate(el => ({ start: el.selectionStart, end: el.selectionEnd, size: el.value.length })))
    .toEqual({ start: 0, end: copied.length, size: copied.length })
  await expect(page.locator('#action-status')).toContainText('手动复制')
  await expect(page.locator('#action-status')).not.toContainText('已复制')
  await expect(page.locator('#share-btn svg')).toHaveCount(1)
  expect(await page.evaluate(() => sharingFallbackCalls)).toEqual(['copy'])
})

test('the single-file offline build shares a canonical HTTPS URL instead of its private filesystem path', async ({ page, context }) => {
  const requests = []
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()) })
  await context.setOffline(true)
  await page.goto(pathToFileURL(resolve('dist/EB1A.html')).href + shareHash())
  await expectReady(page)
  const copied = new URL(await copyLink(page))
  expect(copied.origin).toBe('https://gc.bracketboss2026.com')
  expect(copied.pathname).toBe('/')
  expect(copied.href).not.toContain('EB1A.html')
  expect(new URLSearchParams(copied.hash.slice(1)).get('pd')).toBe('2024-02-29')
  expect(requests).toEqual([])
})

for (const width of [375, 1440]) {
  test(`modify conditions focuses the existing form and cancel restores saved values at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await seedSavedProfile(page)
    await page.goto('./')
    await expectReady(page)
    const button = page.locator('#profile-toggle')
    await expect(button).toHaveAttribute('aria-expanded', String(width >= 768))
    await button.click()
    await expect(page.locator('#pe-cat')).toBeFocused()
    await expect(button).toHaveAttribute('aria-expanded', 'true')
    await page.locator('#pe-cat').selectOption('EB-2')
    await page.locator('#pe-pd-y').fill('2025')
    await page.locator('#pe-cancel').click()
    await expect(page.locator('#pe-cat')).toHaveValue('EB-1A')
    await expect(page.locator('#pe-pd-y')).toHaveValue('2026')
    await expect(button).toHaveAttribute('aria-expanded', String(width >= 768))
    if (width < 768) {
      await expect(page.locator('.profile-rail')).toBeHidden()
      await button.click()
      await expect(page.locator('.profile-rail')).toBeVisible()
      await button.click()
      await expect(page.locator('.profile-rail')).toBeHidden()
      await expect(button).toHaveAttribute('aria-expanded', 'false')
    }
    expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), profileKey)).toEqual(savedProfile)
  })
}

test('reload retains saved conditions and unrelated same-origin CacheStorage entries', async ({ page }) => {
  await seedSavedProfile(page)
  await page.goto('./')
  await expectReady(page)
  await page.evaluate(async () => {
    const cache = await caches.open('sharing-test-other-app')
    await cache.put('./other-app-sentinel', new Response('keep-this-entry'))
    localStorage.setItem('sharing-test-other-app', 'keep-this-setting')
  })
  await Promise.all([page.waitForEvent('load'), page.locator('#refresh-btn').click()])
  await expectReady(page)
  expect(await page.evaluate(async key => {
    const cache = await caches.open('sharing-test-other-app')
    const response = await cache.match('./other-app-sentinel')
    return {
      cached: response ? await response.text() : null,
      setting: localStorage.getItem('sharing-test-other-app'),
      profile: JSON.parse(localStorage.getItem(key)),
      navigation: performance.getEntriesByType('navigation')[0].type
    }
  }, profileKey)).toEqual({ cached: 'keep-this-entry', setting: 'keep-this-setting', profile: savedProfile, navigation: 'reload' })
})
