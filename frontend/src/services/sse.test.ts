import { describe, expect, it } from 'vitest'
import { parseSSEBlocks } from './sse'

describe('parseSSEBlocks', () => {
  it('合并多行 data 并忽略注释', () => {
    const result = parseSSEBlocks(
      ': heartbeat\n'
      + 'event: update\n'
      + 'data: {"message":"第一行",\n'
      + 'data: "value":2}\n\n',
    )

    expect(result.events).toEqual([
      { event: 'update', data: { message: '第一行', value: 2 } },
    ])
    expect(result.remainder).toBe('')
  })

  it('支持 CRLF 和 CR 分隔', () => {
    const result = parseSSEBlocks(
      'event: update\r\ndata: {"part":1}\r\n\r\n'
      + 'event: done\rdata: {"done":true}\r\r',
    )

    expect(result.events.map(event => event.event)).toEqual(['update', 'done'])
    expect(result.events[1].data).toEqual({ done: true })
  })

  it('保留分块边界并在后续调用完成解析', () => {
    const first = parseSSEBlocks('event: update\ndata: {"text":"hel')
    expect(first.events).toEqual([])

    const second = parseSSEBlocks(`${first.remainder}lo"}\n\n`)
    expect(second.events[0]).toEqual({
      event: 'update',
      data: { text: 'hello' },
    })
    expect(second.remainder).toBe('')
  })

  it('flush 解析没有结尾空行的最后事件', () => {
    const result = parseSSEBlocks('data: {"final":true}', true)
    expect(result.events).toEqual([
      { event: 'message', data: { final: true } },
    ])
    expect(result.remainder).toBe('')
  })

  it('忽略没有 data 的块并暴露无效 JSON', () => {
    expect(parseSSEBlocks('event: ping\n\n').events).toEqual([])
    expect(() => parseSSEBlocks('data: not-json\n\n')).toThrow()
  })
})
