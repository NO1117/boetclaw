import { expect, test } from './fixtures/test'

async function sendChat(page: import('@playwright/test').Page, message: string) {
  const input = page.getByPlaceholder('输入任务描述，如：审查钻井报告、生成图表...')
  await expect(input).toBeEnabled()
  await input.fill(message)
  const sendBtn = page.locator('button.send-btn:not(.stop-btn)')
  await expect(sendBtn).toBeEnabled()
  await sendBtn.click()
}

test.describe('login gate', () => {
  test.use({ fakeBackendOptions: { loginRequired: true, consolePassword: 'secret-e2e' } })

  test('错误密码可见失败，正确密码进入控制台', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await expect(page.getByText('管理控制台登录')).toBeVisible()
    await page.getByPlaceholder('控制台密码').fill('wrong')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.locator('.login-error')).toBeVisible()

    await page.getByPlaceholder('控制台密码').fill(fakeBackend.consolePassword)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByRole('heading', { name: '智能对话' })).toBeVisible()
    await expect(page.getByRole('button', { name: /退出/ })).toBeVisible()
  })
})

test.describe('chat / plan / approval / cancel', () => {
  test('默认 Agent 对话返回 fake provider 回声', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: '智能对话' })).toBeVisible()
    await sendChat(page, '审查日报')
    await expect(page.getByText('echo:default:审查日报')).toBeVisible()
    expect(fakeBackend.lastChatBody?.agent_id).toBe('default')
  })

  test('非默认 Agent 计划中断与确认保留服务端 ExecutionRef', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await page.getByRole('button', { name: /default/ }).click()
    await page.getByRole('button', { name: /workspace-a/ }).click()
    await expect(page.getByRole('button', { name: /workspace-a/ })).toBeVisible()

    await sendChat(page, '/plan 生成日报')

    await expect(page.getByText('核对井况')).toBeVisible()
    await expect(page.getByText(/原 Agent：workspace-a/)).toBeVisible()
    await page.getByRole('button', { name: /批准执行/ }).click()
    await expect(page.getByText('计划已继续执行。')).toBeVisible()

    const ref = fakeBackend.lastPlanConfirm?.execution_ref as Record<string, string>
    expect(ref.agent_id).toBe('workspace-a')
    expect(ref.interrupt_type).toBe('plan_confirm')
    expect(ref.interrupt_id).toBeTruthy()
    expect(ref.thread_id).toBeTruthy()
  })

  test('工具审批中断后可批准并清空 pending', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await sendChat(page, '执行 __approval__ 写入')

    await expect(page.getByRole('heading', { name: /工具调用需人工审批：write_file/ }).first()).toBeVisible()
    await page.getByRole('button', { name: /^批准$/ }).first().click()
    await expect(page.getByRole('heading', { name: /工具调用需人工审批/ })).toHaveCount(0)
    expect(fakeBackend.lastApprovalResume?.decision).toBe('approve')
    expect(fakeBackend.approvals.every(a => a.status !== 'pending')).toBeTruthy()
  })

  test('流式运行可停止并得到服务端取消确认', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await sendChat(page, '长任务 __hang__')
    await expect(page.getByTitle('停止运行')).toBeVisible()
    await page.getByTitle('停止运行').click()
    await expect(page.getByText('已停止本地流读取；服务端已确认取消。')).toBeVisible()
    expect(fakeBackend.lastCancelRun).toBeTruthy()
  })

  test('任务详情深链可取消 running 任务', async ({ page, fakeBackend }) => {
    fakeBackend.tasks = [
      {
        id: 'task-e2e-1',
        title: 'E2E 可取消任务',
        prompt: 'long running',
        status: 'running',
        thread_id: 'task-thread-1',
        trace_id: 'task-trace-1',
        run_id: 'task-run-1',
        result: '',
        error: '',
        gateway: '',
        created_at: '2026-07-16T00:00:00Z',
        updated_at: '2026-07-16T00:00:00Z',
      },
    ]

    await page.goto('/tasks/task-e2e-1')
    await expect(page.getByRole('heading', { name: /任务 task-e2e-1/ })).toBeVisible()
    await expect(page.getByRole('main').getByRole('heading', { name: 'E2E 可取消任务' })).toBeVisible()
    // Deep-link load also opens the global task overlay via onTaskUpdate.
    await page.locator('.task-detail-overlay .task-detail').getByRole('button', { name: '取消' }).click()
    await expect(page.locator('.task-detail-overlay .badge.cancelled')).toBeVisible()
    expect(fakeBackend.tasks[0].status).toBe('cancelled')
  })
})

test.describe('domain CRUD and deep links', () => {
  test('井创建、日报 CRUD 与 well_id 深链', async ({ page, fakeBackend }) => {
    await page.goto('/wells')
    await page.getByPlaceholder('井名，如 XX-1').fill('E2E-1')
    await page.getByPlaceholder('区块/油田').fill('测试区块')
    await page.getByRole('button', { name: '创建井' }).click()
    await expect(page.getByText('E2E-1')).toBeVisible()
    expect(fakeBackend.wells).toHaveLength(1)
    const wellId = String(fakeBackend.wells[0].id)

    await page.goto(`/reports?well_id=${wellId}`)
    await expect(page).toHaveURL(new RegExp(`/reports\\?well_id=${wellId}`))
    await expect(page.getByRole('heading', { name: '钻井日报' })).toBeVisible()

    await page.locator('input[type="date"]').fill('2026-07-16')
    await page.getByPlaceholder('起始井深').fill('100')
    await page.getByPlaceholder('结束井深').fill('200')
    await page.getByPlaceholder('日报摘要').fill('E2E 日报摘要')
    await page.getByRole('button', { name: '保存日报' }).click()
    await expect(page.getByText(/E2E 日报摘要/)).toBeVisible()
    expect(fakeBackend.reports).toHaveLength(1)

    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: '删除' }).click()
    await expect(page.getByText(/E2E 日报摘要/)).toHaveCount(0)
    expect(fakeBackend.reports).toHaveLength(0)
  })

  test('设置与任务深链刷新保持路由', async ({ page }) => {
    await page.goto('/settings/security')
    await expect(page).toHaveURL(/\/settings\/security$/)
    await expect(page.getByRole('button', { name: '安全' })).toBeVisible()
    await expect(page.getByText('ToolGuard 策略')).toBeVisible()
    await page.reload()
    await expect(page).toHaveURL(/\/settings\/security$/)
    await expect(page.getByText('ToolGuard 策略')).toBeVisible()

    await page.goto('/agents/workspace-a')
    await expect(page).toHaveURL(/\/agents\/workspace-a$/)
    await expect(page.getByRole('heading', { name: /Agent workspace-a/ })).toBeVisible()
  })
})
