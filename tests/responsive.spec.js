const { test, expect } = require('@playwright/test')

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error })
})

async function openSaved(page) {
  await page.addInitScript(() => {
    if (!localStorage.getItem('eb1a_user_profile')) localStorage.setItem('eb1a_user_profile', JSON.stringify({
      pd: Date.UTC(2024, 0, 15), category: 'EB-3', country: 'CN', path: 'AOS', family: 0, chartType: 'A'
    }))
  })
  await page.goto('./')
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#hero-value')).not.toHaveText('--')
}

for (const width of [375, 768, 1024, 1440, 1920]) {
  test(`responsive workspace at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await openSaved(page)
    await expect(page.locator('#gc-root')).toHaveAttribute('data-ui', 'heroui-pro')
    await expect(page.locator('.widget')).toHaveCount(4)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    if (width >= 768) {
      await expect(page.locator('.profile-widget')).toBeVisible()
      await expect(page.locator('#pe-pd-y')).toHaveValue('2024')
      const rail = await page.locator('.profile-rail').boundingBox()
      const main = await page.locator('main').boundingBox()
      expect(rail.x + rail.width).toBeLessThan(main.x)
      if (width >= 1440) expect(main.width).toBeGreaterThan(width * .6)
    } else {
      await expect(page.locator('.profile-rail')).toBeHidden()
    }
    await page.getByRole('tab', { name: '高级设置' }).click()
    await page.locator('[data-pace="recent"]').click()
    await expect(page.locator('[data-pace="recent"]')).toHaveClass(/active/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    const strip = await page.locator('.tab-strip').boundingBox()
    expect(strip.height).toBeLessThan(80)
  })
}

test('welcome entry synchronizes the desktop profile without a reload', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('./')
  await page.locator('#wf-cat').selectOption('EB-3')
  await page.locator('#wf-pd-y').fill('2024')
  await page.locator('#wf-pd-m').fill('01')
  await page.locator('#wf-pd-d').fill('15')
  await page.locator('#wf-start').click()
  await expect(page.locator('#welcome-modal')).toBeHidden()
  await expect(page.locator('#pe-pd-y')).toHaveValue('2024')
  await expect(page.locator('#pe-pd-m')).toHaveValue('1')
  await expect(page.locator('#pe-pd-d')).toHaveValue('15')
  await expect(page.locator('#pe-cat')).toHaveValue('EB-3')
})

test('mobile profile cancel restores values and save persists changes', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await openSaved(page)
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(page.locator('#pe-pd-y')).toHaveValue('2024')
  await page.locator('#pe-pd-y').fill('2025')
  await page.locator('#pe-cancel').click()
  await expect(page.locator('.profile-rail')).toBeHidden()
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(page.locator('#pe-pd-y')).toHaveValue('2024')
  await page.locator('#pe-pd-y').fill('2025')
  await page.locator('#pe-save').click()
  await expect(page.locator('.profile-rail')).toBeHidden()
  await expect(page.locator('#pv-pd')).toHaveText('2025-01-15')
  await page.reload()
  await expect(page.locator('#pv-pd')).toHaveText('2025-01-15')
})

test('theme and keyboard scenario controls work', async ({ page }) => {
  await openSaved(page)
  await page.getByRole('button', { name: '切换深色模式' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('button', { name: '切换浅色模式' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: '乐观情景' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('[data-pct="p10"]')).toHaveClass(/selected/)
})

test('Current queues hide the whole chart widget and restore it after switching', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await openSaved(page)
  await page.locator('#pe-cat').selectOption('EB-5-Rural')
  await page.locator('#pe-save').click()
  await expect(page.locator('#hero-value')).toHaveText('Current')
  await expect(page.locator('.chart-widget')).toBeHidden()
  await page.locator('#pe-cat').selectOption('EB-3')
  await page.locator('#pe-save').click()
  await expect(page.locator('.chart-widget')).toBeVisible()
})
