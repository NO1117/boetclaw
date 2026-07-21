import { expect, test } from './fixtures/test'

async function sendChat(page: import('@playwright/test').Page, message: string) {
  const input = page.getByLabel('消息输入')
  await expect(input).toBeEnabled()
  await input.fill(message)
  const sendBtn = page.getByRole('button', { name: '发送消息' })
  await expect(sendBtn).toBeEnabled()
  await sendBtn.click()
}

async function attachTextFile(
  page: import('@playwright/test').Page,
  filename: string,
  content: string,
) {
  await expect(page.getByRole('heading', { name: 'BoetClaw Agent 工作台' })).toBeVisible()
  await expect(page.getByRole('button', { name: '添加文件', exact: true })).toBeVisible()
  const fileInput = page.locator('input[type="file"]:not([accept]):not([webkitdirectory])')
  await expect(fileInput).toBeAttached()
  await fileInput.setInputFiles({
    name: filename,
    mimeType: 'text/plain',
    buffer: Buffer.from(content),
  })
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
    await expect(page.getByRole('heading', { name: '对话工作台' })).toBeVisible()
    await expect(page.getByRole('button', { name: /退出/ })).toBeVisible()
  })
})

test.describe('chat / plan / approval / cancel', () => {
  test('默认 Agent 对话返回 fake provider 回声', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: 'BoetClaw Agent 工作台' })).toBeVisible()
    await sendChat(page, '审查日报')
    await expect(page.getByText('echo:default:审查日报')).toBeVisible()
    expect(fakeBackend.lastChatBody?.agent_id).toBe('default')
  })

  test('附件与模型字段会进入 chat stream 请求', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await attachTextFile(page, 'notes.txt', 'hello attachment')
    await expect(page.getByText('notes.txt')).toBeVisible()
    await expect(page.getByRole('button', { name: '发送消息' })).toBeEnabled({ timeout: 15_000 })
    await page.getByLabel('消息输入').fill('请阅读附件')
    await page.getByRole('button', { name: '发送消息' }).click()
    await expect(page.getByText('echo:default:请阅读附件:attachment_ids=1')).toBeVisible()
    expect(Array.isArray(fakeBackend.lastChatBody?.attachment_ids)).toBeTruthy()
    expect(fakeBackend.lastChatBody?.provider).toBe('fake')
    expect(fakeBackend.lastChatBody?.model).toBe('fake-model')
  })

  test('上传 fixture 后通过 attachment id 发送并展示引用', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await attachTextFile(page, 'fixture.txt', 'fixture citation text')
    await expect(page.getByText('fixture.txt')).toBeVisible()
    await expect(page.getByRole('button', { name: '发送消息' })).toBeEnabled({ timeout: 15_000 })
    await page.getByLabel('消息输入').fill('引用文档')
    await page.getByRole('button', { name: '发送消息' }).click()
    await expect(page.getByText(/attachment_ids=1/)).toBeVisible()
    await expect(page.getByText('▧ fixture.txt · 21 B')).toBeVisible()
    expect(Object.keys(fakeBackend.attachments).length).toBeGreaterThan(0)
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
    await expect(page.getByLabel('停止运行')).toBeVisible()
    await page.getByLabel('停止运行').click()
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
    await page.locator('.task-detail-overlay .task-detail').getByRole('button', { name: '取消' }).click()
    await expect(page.locator('.task-detail-overlay .badge.cancelled')).toBeVisible()
    expect(fakeBackend.tasks[0].status).toBe('cancelled')
  })
})

test.describe('routing and agent workspace', () => {
  test('旧领域路由显示已移除提示', async ({ page }) => {
    await page.goto('/wells')
    await expect(page.getByRole('main').getByRole('heading', { name: '页面已移除' })).toBeVisible()
    await expect(page.getByText(/钻井领域模块/)).toBeVisible()

    await page.goto('/reports')
    await expect(page.getByRole('main').getByRole('heading', { name: '页面已移除' })).toBeVisible()

    await page.goto('/artifacts')
    await expect(page.getByRole('main').getByRole('heading', { name: '页面已移除' })).toBeVisible()
  })

  test('设置与 Agent 深链刷新保持路由', async ({ page }) => {
    await page.goto('/settings/security')
    await expect(page).toHaveURL(/\/settings\/security$/)
    await expect(page.getByText('ToolGuard 策略')).toBeVisible()

    await page.goto('/agents/workspace-a')
    await expect(page).toHaveURL(/\/agents\/workspace-a$/)
    await expect(page.getByRole('heading', { name: 'Agent workspace-a' })).toBeVisible()
    await expect(page.getByPlaceholder('搜索 Agent…')).toBeVisible()
  })
})
