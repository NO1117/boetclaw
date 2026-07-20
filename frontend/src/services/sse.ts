export interface ParsedSSEBlock {
  event: string
  data: unknown
}

export interface SSEParseResult {
  events: ParsedSSEBlock[]
  remainder: string
}

function parseBlock(block: string): ParsedSSEBlock | null {
  let event = 'message'
  const data: string[] = []

  for (const rawLine of block.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')) {
    if (!rawLine || rawLine.startsWith(':')) continue
    const colon = rawLine.indexOf(':')
    const field = colon < 0 ? rawLine : rawLine.slice(0, colon)
    let value = colon < 0 ? '' : rawLine.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    if (field === 'data') data.push(value)
  }

  if (data.length === 0) return null
  const text = data.join('\n')
  return { event, data: JSON.parse(text) as unknown }
}

/** Parse complete SSE blocks while preserving an incomplete chunk boundary. */
export function parseSSEBlocks(input: string, flush = false): SSEParseResult {
  const events: ParsedSSEBlock[] = []
  let remainder = input

  while (remainder) {
    const match = /\r\n\r\n|\n\n|\r\r/.exec(remainder)
    if (!match) break
    const block = remainder.slice(0, match.index)
    remainder = remainder.slice(match.index + match[0].length)
    const parsed = parseBlock(block)
    if (parsed) events.push(parsed)
  }

  if (flush && remainder.trim()) {
    const parsed = parseBlock(remainder)
    if (parsed) events.push(parsed)
    remainder = ''
  }
  return { events, remainder }
}
