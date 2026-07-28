import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import TeamPermissionsPage from '../components/TeamPermissionsPage'
import { fetchMock, installFetchMock, mockJson } from '../test/fetchMock'

beforeEach(() => {
  fetchMock.mockReset()
  installFetchMock()
})

describe('TeamPermissionsPage', () => {
  it('lists users and hides create form for viewers', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({
        users: [
          {
            id: 'u1',
            username: 'alice',
            display_name: 'Alice',
            role: 'operator',
            status: 'active',
          },
        ],
      }),
    )
    render(
      <TeamPermissionsPage
        currentUser={{ role: 'viewer', permissions: ['users:read'] }}
      />,
    )
    expect(await screen.findByText('Alice')).toBeInTheDocument()
    expect(screen.queryByText('创建用户')).not.toBeInTheDocument()
  })

  it('allows owner to create users', async () => {
    fetchMock
      .mockResolvedValueOnce(mockJson({ users: [] }))
      .mockResolvedValueOnce(
        mockJson({
          id: 'u2',
          username: 'bob',
          display_name: 'Bob',
          role: 'operator',
          status: 'active',
        }),
      )
      .mockResolvedValueOnce(
        mockJson({
          users: [
            {
              id: 'u2',
              username: 'bob',
              display_name: 'Bob',
              role: 'operator',
              status: 'active',
            },
          ],
        }),
      )
    render(
      <TeamPermissionsPage
        currentUser={{
          role: 'owner',
          permissions: ['users:read', 'users:write'],
        }}
      />,
    )
    expect(await screen.findByText('创建用户')).toBeInTheDocument()
    await userEvent.type(screen.getByPlaceholderText('用户名'), 'bob')
    await userEvent.type(screen.getByPlaceholderText('初始密码（至少 8 位）'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: '创建' }))
    expect(await screen.findByText('Bob')).toBeInTheDocument()
  })
})
