/**
 * Optional / manual suite — real Provider or channel connectivity.
 *
 * Not part of the default PR gate (`npm run test:e2e`).
 * Run explicitly when credentials and network are available:
 *
 *   npx playwright test --project=manual-real-provider
 *
 * Requires a live backend (not the Playwright fake route backend) with real
 * provider credentials configured via environment / settings.
 */
import { expect, test } from '@playwright/test'

const realBase = process.env.E2E_REAL_BASE_URL
const realPassword = process.env.E2E_CONSOLE_PASSWORD

test.describe('manual real provider / channel', () => {
  test.skip(!realBase, 'Set E2E_REAL_BASE_URL to run against a live stack')

  test.use({
    baseURL: realBase,
  })

  test('控制台可达且健康检查通过', async ({ page, request }) => {
    const health = await request.get(`${realBase?.replace(/\/$/, '')}/api/v1/health`)
    expect(health.ok()).toBeTruthy()

    await page.goto('/chat')
    if (realPassword) {
      const passwordInput = page.getByPlaceholder('控制台密码')
      if (await passwordInput.isVisible().catch(() => false)) {
        await passwordInput.fill(realPassword)
        await page.getByRole('button', { name: '登录' }).click()
      }
    }
    await expect(page.getByRole('heading', { name: '智能对话' })).toBeVisible()
  })

  test('真实 Provider 对话（需已配置模型）', async ({ page }) => {
    test.skip(!process.env.E2E_REAL_PROVIDER, 'Set E2E_REAL_PROVIDER=1 to exercise live LLM')
    await page.goto('/chat')
    if (realPassword) {
      const passwordInput = page.getByPlaceholder('控制台密码')
      if (await passwordInput.isVisible().catch(() => false)) {
        await passwordInput.fill(realPassword)
        await page.getByRole('button', { name: '登录' }).click()
      }
    }
    await page.getByPlaceholder('输入任务描述，如：审查钻井报告、生成图表...').fill('用一句话介绍你自己')
    await page.getByRole('button', { name: '发送' }).click()
    await expect(page.locator('.message.assistant').last()).toBeVisible({ timeout: 120_000 })
    await expect(page.locator('.message.assistant').last()).not.toContainText(/^错误:/)
  })
})
