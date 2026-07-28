import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import KnowledgeCitationCard from './KnowledgeCitationCard'

describe('KnowledgeCitationCard', () => {
  it('renders citations and triggers preview', async () => {
    const onPreview = vi.fn()
    render(
      <KnowledgeCitationCard
        citations={[{
          knowledge_base_id: 'kb1',
          knowledge_base_name: '测试库',
          document_id: 'doc1',
          document_name: '手册.pdf',
          chunk_id: 'doc1-c0000',
          location: { page: 3 },
          score: 2,
          truncated: false,
          snippet: '示例片段',
        }]}
        onPreview={onPreview}
      />,
    )
    expect(screen.getByText('知识库引用')).toBeInTheDocument()
    await userEvent.click(screen.getByText('手册.pdf'))
    expect(onPreview).toHaveBeenCalled()
  })
})
