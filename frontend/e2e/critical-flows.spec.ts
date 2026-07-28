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
    await expect(page.getByLabel('附件队列').getByText('fixture.txt')).toBeVisible()
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

async function attachImageFile(page: import('@playwright/test').Page, filename: string) {
  await expect(page.getByRole('button', { name: '添加图片' })).toBeVisible()
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  )
  await page.locator('input[accept="image/*"]').setInputFiles({
    name: filename,
    mimeType: 'image/png',
    buffer: png,
  })
}

test.describe('model capability and run metrics', () => {
  test('图片附件时 text-pro 不可选', async ({ page, fakeBackend: _fakeBackend }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: 'BoetClaw Agent 工作台' })).toBeVisible()
    await attachImageFile(page, 'screenshot.png')
    await expect(page.getByText('screenshot.png')).toBeVisible()
    await page.getByLabel('选择模型').click()
    await expect(page.getByText('已检测到 1 张图片 · 需要视觉理解能力')).toBeVisible()
    await expect(page.getByRole('option', { name: /text-pro/ })).toBeDisabled()
    await expect(page.getByText('不可选：当前图片需要视觉能力')).toBeVisible()
  })

  test('兼容模型发送后展示本次运行指标', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await attachTextFile(page, 'metrics.txt', 'metrics fixture')
    await expect(page.getByRole('button', { name: '发送消息' })).toBeEnabled({ timeout: 15_000 })
    await page.getByLabel('消息输入').fill('读取指标')
    await page.getByRole('button', { name: '发送消息' }).click()
    await expect(page.getByText('echo:default:读取指标:attachment_ids=1')).toBeVisible()
    await expect(page.getByLabel('本次运行')).toBeVisible()
    await expect(page.getByText('● 已完成')).toBeVisible()
    await expect(page.getByText(/首字 800ms/)).toBeVisible()
    await expect(page.getByText(/输入 3,842/)).toBeVisible()
    expect(fakeBackend.lastChatBody?.provider).toBe('fake')
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

    await page.goto('/settings/providers')
    await expect(page.getByRole('heading', { level: 3, name: '模型连接' })).toBeVisible()

    await page.goto('/agents/workspace-a')
    await expect(page).toHaveURL(/\/agents\/workspace-a$/)
    await expect(page.getByRole('heading', { name: 'workspace-a' })).toBeVisible()
    await expect(page.getByPlaceholder('搜索 Agent…')).toBeVisible()
    await expect(page.getByRole('tab', { name: '配置' })).toBeVisible()
  })
})

test.describe('agent configuration studio', () => {
  test('配置页可验证并保存 Agent 配置', async ({ page }) => {
    await page.goto('/agents/workspace-a')
    await page.getByRole('tab', { name: '配置' }).click()
    await expect(page.getByLabel('职责提示词')).toBeVisible()
    await page.getByLabel('职责提示词').fill('E2E 测试职责提示词')
    await page.getByRole('button', { name: '验证配置' }).click()
    await expect(page.getByText('验证通过，可保存配置')).toBeVisible()
    await page.getByRole('button', { name: '保存并应用' }).click()
    await expect(page.getByText('配置已保存并应用')).toBeVisible()
  })

  test('版本页可预览差异', async ({ page }) => {
    await page.goto('/agents/default')
    await page.getByRole('tab', { name: '版本' }).click()
    await page.getByRole('button', { name: '差异' }).first().click()
    await expect(page.getByText(/与当前差异/)).toBeVisible()
  })

  test('创建向导可仅填 ID 创建 Agent', async ({ page }) => {
    await page.goto('/agents/default')
    await page.getByRole('button', { name: '新建', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '创建 Agent' })).toBeVisible()
    await page.getByLabel('Agent ID').fill('e2e-studio-agent')
    await page.getByRole('button', { name: '下一步' }).click()
    await page.getByRole('button', { name: '下一步' }).click()
    await page.getByRole('button', { name: '下一步' }).click()
    await page.getByRole('button', { name: '下一步' }).click()
    await page.getByRole('button', { name: '创建 Agent' }).click()
    await expect(page.getByRole('heading', { name: 'e2e-studio-agent' })).toBeVisible()
  })
})

test.describe('voice capabilities', () => {
  test('设置页展示 fake 语音能力状态', async ({ page, fakeBackend }) => {
    await page.goto('/settings/providers')
    await expect(page.getByLabel('语音能力状态')).toBeVisible()
    await expect.poll(() => fakeBackend.lastVoiceCapabilities).not.toBeNull()
    await expect(page.getByText('● 服务端已配置')).toBeVisible()
    await expect(page.getByText('fake-stt')).toBeVisible()
  })
})

test.describe('persistent memory', () => {
  test('设置页可管理长期记忆', async ({ page }) => {
    await page.goto('/settings/memory')
    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 3, name: '长期记忆' })).toBeVisible()
    await page.getByPlaceholder('手动新增一条长期记忆…').fill('E2E 手动记忆条目')
    await page.locator('.memory-create-row').getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.getByText('E2E 手动记忆条目')).toBeVisible()
  })

  test('对话上下文展示记忆摘要卡', async ({ page }) => {
    await page.goto('/chat')
    await sendChat(page, '__memory_used__ 测试')
    const memoryCard = page.locator('.memory-context-card')
    await expect(memoryCard.getByRole('heading', { name: '长期记忆' })).toBeVisible()
    await expect(memoryCard.getByText('本次使用')).toBeVisible()
    await expect(memoryCard.locator('dd').filter({ hasText: /^1$/ })).toBeVisible()
  })

  test('候选记忆确认条可批准', async ({ page, fakeBackend }) => {
    await page.goto('/chat')
    await sendChat(page, '__memory_candidate__ 偏好')
    await expect(page.getByText('检测到可保存的长期记忆')).toBeVisible()
    await page.locator('.memory-candidate-bar').getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.getByText('检测到可保存的长期记忆')).toHaveCount(0)
    expect(fakeBackend.memories['mem-pending-1']?.status).toBe('active')
  })
})

test.describe('knowledge base flow', () => {
  test('创建知识库 → 上传 → 绑定 → 对话选择 → 显示引用', async ({ page, fakeBackend }) => {
    await page.goto('/knowledge')
    await expect(page.getByRole('heading', { level: 1, name: '知识库' })).toBeVisible()
    await page.getByLabel('新库名称').fill('E2E 知识库')
    await page.getByRole('button', { name: '创建' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'E2E 知识库' })).toBeVisible()

    const kbId = Object.keys(fakeBackend.knowledgeBases)[0]
    expect(kbId).toBeTruthy()

    const uploadInput = page.locator('.knowledge-base-page input[type="file"]')
    await uploadInput.setInputFiles({
      name: 'fixture-kb.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('fixture kb content'),
    })
    await expect(page.getByText('fixture-kb.txt')).toBeVisible({ timeout: 10_000 })

    await page.goto('/agents/default')
    await page.getByRole('tab', { name: '知识库' }).click()
    await page.getByRole('button', { name: '绑定' }).click()
    await expect(page.getByText('解绑')).toBeVisible()

    await page.goto('/chat')
    await page.getByLabel('选择知识库').selectOption({ label: 'E2E 知识库' })
    await sendChat(page, '查询知识库内容')
    await expect(page.getByText(/:kb=1/)).toBeVisible()
    await expect(page.getByText('知识库引用')).toBeVisible()
    await expect(page.getByText('fixture-kb.txt')).toBeVisible()
  })
})

test.describe('provider connections', () => {
  test('完整连接管理流程且密钥不可回读', async ({ page, fakeBackend }) => {
    await page.goto('/settings/providers')
    await expect(page.getByRole('heading', { name: '模型连接' })).toBeVisible()
    await expect(page.getByText('Fake 默认连接')).toBeVisible()

    await page.getByRole('button', { name: '新建连接' }).click()
    await page.getByPlaceholder('显示名称').fill('E2E OpenAI')
    await page.getByPlaceholder('API Key').fill('sk-e2e-secret-key-9999')
    await page.getByPlaceholder('默认模型').fill('fake-model')
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('连接已创建')).toBeVisible()
    const newRow = page.locator('.mgr-item').filter({ hasText: 'E2E OpenAI' })
    await expect(newRow).toBeVisible()
    await expect(page.getByText('sk-e2e')).not.toBeVisible()

    const connIds = Object.keys(fakeBackend.providerConnections)
    const newId = connIds.find(id => id.startsWith('conn-e2e-'))
    expect(newId).toBeTruthy()
    const conn = fakeBackend.providerConnections[newId!]
    expect(conn.credential_fingerprint).toBe('e2e1')
    expect(JSON.stringify(conn)).not.toContain('sk-e2e-secret')

    await newRow.getByRole('button', { name: '检测' }).click()
    await expect.poll(() => fakeBackend.providerConnections[newId!]?.last_check?.connected).toBe(true)

    await newRow.getByRole('button', { name: '设为默认' }).click()
    await expect(page.getByText('已设为默认连接')).toBeVisible()
  })
})

test.describe('durable task queue runtime center', () => {
  test('创建计划任务、队列控制与详情尝试时间线', async ({ page, fakeBackend }) => {
    await page.goto('/tasks')
    await expect(page.getByRole('heading', { name: '运行中心' })).toBeVisible()

    await page.locator('.panel-actions').getByRole('button', { name: '新建', exact: true }).click()
    await page.getByPlaceholder('任务标题').fill('E2E 持久化任务')
    await page.getByPlaceholder('任务描述 / Prompt').fill('scheduled durable flow')
    const future = new Date(Date.now() + 3600_000)
    const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16)
    await page.locator('input[type="datetime-local"]').fill(local)
    await page.getByRole('button', { name: '提交任务' }).click()

    await expect(page.getByText('E2E 持久化任务')).toBeVisible()
    expect(fakeBackend.tasks.some(t => t.title === 'E2E 持久化任务')).toBeTruthy()

    await page.getByRole('button', { name: '暂停' }).click()
    await expect(page.getByText('已暂停')).toBeVisible()

    await page.getByText('E2E 持久化任务').click()
    await expect(page.getByRole('main').getByText('scheduled durable flow')).toBeVisible()
  })
})
