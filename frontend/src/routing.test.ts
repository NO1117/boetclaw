import { describe, expect, it } from 'vitest'
import { isRemovedLegacyPath, parseRoute } from './App'

describe('parseRoute', () => {
  it('解析通用工作台路由', () => {
    expect(parseRoute('/chat')).toEqual({ page: 'chat' })
    expect(parseRoute('/tasks/task-1')).toEqual({ page: 'tasks', taskId: 'task-1' })
    expect(parseRoute('/agents/workspace-a')).toEqual({ page: 'agents', agentId: 'workspace-a' })
    expect(parseRoute('/trace/trace-1')).toEqual({ page: 'trace', traceId: 'trace-1' })
    expect(parseRoute('/settings/security')).toEqual({ page: 'settings', settingsTab: 'security' })
    expect(parseRoute('/settings/team')).toEqual({ page: 'settings', settingsTab: 'team' })
  })

  it('旧领域路由进入 removed 页面', () => {
    for (const path of ['/wells', '/wells/abc', '/reports', '/params', '/las/import', '/artifacts']) {
      expect(parseRoute(path)).toEqual({ page: 'removed', removedPath: path })
    }
  })

  it('未知路径进入 not-found', () => {
    expect(parseRoute('/unknown')).toEqual({ page: 'not-found' })
  })
})

describe('isRemovedLegacyPath', () => {
  it('识别领域遗留路径', () => {
    expect(isRemovedLegacyPath('/wells')).toBe(true)
    expect(isRemovedLegacyPath('/agents/default')).toBe(false)
  })
})
