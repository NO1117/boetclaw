import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MemoryContextCard from './MemoryContextCard'

describe('MemoryContextCard', () => {
  it('renders summary counts', () => {
    render(
      <MemoryContextCard
        summary={{
          mode: 'review',
          backend: 'sqlite',
          persistent: true,
          saved_count: 3,
          used_count: 1,
          pending_count: 2,
          injected_chars: 40,
          items: [{ id: 'm1', scope: 'agent', summary: '偏好中文' }],
        }}
      />,
    )
    expect(screen.getByText('review')).toBeInTheDocument()
    expect(screen.getByText('偏好中文')).toBeInTheDocument()
  })
})
