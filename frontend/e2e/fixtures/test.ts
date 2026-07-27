import { test as base, expect } from '@playwright/test'
import {
  installFakeBackend,
  type FakeBackendOptions,
  type FakeStore,
} from './fakeBackend'

type Fixtures = {
  fakeBackend: FakeStore
  fakeBackendOptions: FakeBackendOptions
}

export const test = base.extend<Fixtures>({
  fakeBackendOptions: [{}, { option: true }],

  fakeBackend: [async ({ page, context, fakeBackendOptions }, use, testInfo) => {
    const logs: string[] = []
    page.on('console', msg => {
      logs.push(`[${msg.type()}] ${msg.text()}`)
    })
    page.on('pageerror', err => {
      logs.push(`[pageerror] ${err.message}`)
    })
    page.on('requestfailed', req => {
      logs.push(`[requestfailed] ${req.method()} ${req.url()} :: ${req.failure()?.errorText ?? ''}`)
    })

    await context.addInitScript(() => {
      try {
        localStorage.removeItem('boetclaw_console_token')
      } catch {
        // ignore
      }
    })

    // Context-level routes intercept before any page navigation / Vite proxy.
    const store = await installFakeBackend(page, fakeBackendOptions, context)
    await use(store)

    if (testInfo.status !== testInfo.expectedStatus) {
      await testInfo.attach('browser-logs', {
        body: logs.join('\n') || '(no browser logs)',
        contentType: 'text/plain',
      })
      await testInfo.attach('fake-backend-snapshot', {
        body: JSON.stringify(
          {
            lastChatBody: store.lastChatBody,
            lastPlanConfirm: store.lastPlanConfirm,
            lastApprovalResume: store.lastApprovalResume,
            lastCancelRun: store.lastCancelRun,
            wells: store.wells,
            tasks: store.tasks,
            approvals: store.approvals,
          },
          null,
          2,
        ),
        contentType: 'application/json',
      })
    }

    store.releaseHangStreams()
  }, { auto: true }],
})

export { expect }
