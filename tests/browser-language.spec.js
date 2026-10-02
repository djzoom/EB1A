const { test: base, expect } = require('@playwright/test')
const { resolve } = require('node:path')
const { pathToFileURL } = require('node:url')

const locales = ['zh-CN', 'hi', 'es', 'pt-BR', 'ja', 'ko', 'ar', 'de', 'fr', 'it']
const profile = {
  pd: Date.UTC(2026, 0, 15), category: 'EB-1A', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
}
const test = base.extend({
  page: async ({ page }, use) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await use(page)
    expect(errors, '浏览器语言初始化和手动切换不应产生页面异常').toEqual([])
  }
})

async function preferences(page, { languages, language, saved = null, savedProfile = false, blocked = false }) {
  await page.addInitScript(config => {
    // window.name 在同源刷新后保留，用于模拟浏览器偏好改变，避免叠加初始化脚本的顺序依赖。
    const browser = window.name.startsWith('gc-test-browser:')
      ? JSON.parse(window.name.slice('gc-test-browser:'.length)) : config
    Object.defineProperty(Navigator.prototype, 'languages', { configurable: true, get: () => browser.languages })
    Object.defineProperty(Navigator.prototype, 'language', { configurable: true, get: () => browser.language })
    if (config.blocked) {
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        get() { throw new DOMException('Storage disabled for this test', 'SecurityError') }
      })
      return
    }
    if (config.savedProfile && !localStorage.getItem('eb1a_user_profile')) {
      localStorage.setItem('eb1a_user_profile', JSON.stringify(config.profile))
    }
    if (config.saved !== null && !localStorage.getItem('gc_language')) {
      localStorage.setItem('gc_language', config.saved)
    }
  }, { languages, language, saved, savedProfile, blocked, profile })
}

async function expectLocale(page, locale) {
  await expect(page.locator('html')).toHaveAttribute('lang', locale)
  await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr')
  for (const selector of ['#language-select', '#welcome-language-select']) {
    await expect(page.locator(selector)).toHaveValue(locale)
    await expect(page.locator(`${selector} option`)).toHaveCount(locales.length)
    expect(await page.locator(`${selector} option`).evaluateAll(options => options.map(option => option.value))).toEqual(locales)
  }
}

for (const [region, locale] of [
  ['zh-TW', 'zh-CN'], ['hi-IN', 'hi'], ['es-MX', 'es'], ['pt-PT', 'pt-BR'], ['ja-JP', 'ja'],
  ['ko-KR', 'ko'], ['ar-EG', 'ar'], ['de-AT', 'de'], ['fr-CA', 'fr'], ['it-CH', 'it']
]) {
  test(`first visit maps browser ${region} to ${locale} without saving an automatic preference`, async ({ page }) => {
    await preferences(page, { languages: [region, 'en-US'], language: 'en-US' })
    await page.goto('./')
    await expectLocale(page, locale)
    await expect(page.locator('#welcome-modal')).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBeNull()
    expect(await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))).toBeNull()
  })
}

test('browser preferences skip unsupported languages and use the first supported language before navigator.language', async ({ page }) => {
  await preferences(page, { languages: ['en-US', 'fr-CA', 'ja-JP'], language: 'es-MX' })
  await page.goto('./')
  await expectLocale(page, 'fr')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBeNull()
})

test('empty browser preference list falls back to navigator.language', async ({ page }) => {
  await preferences(page, { languages: [], language: 'de-CH' })
  await page.goto('./')
  await expectLocale(page, 'de')
})

test('unsupported browser preferences and navigator.language fall back to Chinese', async ({ page }) => {
  await preferences(page, { languages: ['en-US', 'nl-NL'], language: 'sv-SE' })
  await page.goto('./')
  await expectLocale(page, 'zh-CN')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBeNull()
})

test('invalid stored and shared languages fall through to the supported browser language', async ({ page }) => {
  await preferences(page, { languages: ['es-MX'], language: 'en-US', saved: 'not-a-language' })
  await page.goto('./#lang=unsupported')
  await expectLocale(page, 'es')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBe('not-a-language')
})

test('a valid saved manual preference takes priority over the browser without changing profile conditions', async ({ page }) => {
  await preferences(page, { languages: ['ar-EG'], language: 'ar-EG', saved: 'fr', savedProfile: true })
  await page.goto('./')
  await expectLocale(page, 'fr')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('eb1a_user_profile')))).toEqual(profile)
})

test('automatic choices follow changed browser preferences on reload while a manual choice persists', async ({ page }) => {
  await preferences(page, { languages: ['fr-CA'], language: 'fr-CA', savedProfile: true })
  await page.goto('./')
  await expectLocale(page, 'fr')
  const saved = await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))
  await page.evaluate(() => { window.name = 'gc-test-browser:' + JSON.stringify({ languages: ['de-AT'], language: 'de-AT' }) })
  await page.reload()
  await expectLocale(page, 'de')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBeNull()
  await page.locator('#language-select').selectOption('it')
  await expectLocale(page, 'it')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBe('it')
  await page.evaluate(() => { window.name = 'gc-test-browser:' + JSON.stringify({ languages: ['ar-EG'], language: 'ar-EG' }) })
  await page.reload()
  await expectLocale(page, 'it')
  expect(await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))).toBe(saved)
})

test('a valid shared language wins over saved and browser languages without overwriting either saved preference or profile', async ({ page }) => {
  await preferences(page, { languages: ['de-AT'], language: 'de-AT', saved: 'fr', savedProfile: true })
  const hash = new URLSearchParams({ share: '1', category: 'EB-3', country: 'IN', pd: '2024-02-29', lang: 'ar' })
  await page.goto(`./#${hash}`)
  await expectLocale(page, 'ar')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBe('fr')
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('eb1a_user_profile')))).toEqual(profile)
  await expect(page.locator('#pv-pd')).toHaveText('2024-02-29')
})

test('blocked localStorage still allows browser initialization and a manual language change', async ({ page }) => {
  await preferences(page, { languages: ['hi-IN'], language: 'en-US', blocked: true })
  await page.goto('./')
  await expectLocale(page, 'hi')
  await expect(page.locator('#welcome-modal')).toBeVisible()
  await page.locator('#welcome-language-select').selectOption('ko')
  await expectLocale(page, 'ko')
})

test('offline single HTML follows the browser and keeps exactly ten language options with no network requests', async ({ page, context }) => {
  const requests = []
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()) })
  await preferences(page, { languages: ['en-US', 'pt-PT'], language: 'en-US', savedProfile: true })
  await context.setOffline(true)
  await page.goto(pathToFileURL(resolve('dist/EB1A.html')).href)
  await expectLocale(page, 'pt-BR')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBeNull()
  const saved = await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))
  await page.locator('#language-select').selectOption('ja')
  await page.reload()
  await expectLocale(page, 'ja')
  expect(await page.evaluate(() => localStorage.getItem('gc_language'))).toBe('ja')
  expect(await page.evaluate(() => localStorage.getItem('eb1a_user_profile'))).toBe(saved)
  expect(requests).toEqual([])
})
