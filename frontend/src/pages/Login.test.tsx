import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import LoginPage from './Login'

const navigateMock = vi.fn()
const setBuyerWalletMock = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({
    setBuyerWallet: setBuyerWalletMock,
  }),
}))

vi.mock('../utils/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    login: vi.fn(async () => ({
      user_id: 'user-123',
      session_token: 'session-abc',
      algo_address: 'TESTALGOWALLETADDRESS111111111111111111111111111111111',
      message: 'Logged in',
    })),
  },
}))

describe('LoginPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    setBuyerWalletMock.mockReset()
    localStorage.clear()
  })

  it('submits login credentials and stores the session', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'buyer@example.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'correct horse battery staple' } })
    fireEvent.submit(screen.getByRole('button', { name: /sign in/i }).closest('form') as HTMLFormElement)

    expect(await screen.findByText(/logged in successfully/i)).toBeInTheDocument()
    expect(setBuyerWalletMock).toHaveBeenCalledWith('TESTALGOWALLETADDRESS111111111111111111111111111111111')

    const storedSession = JSON.parse(localStorage.getItem('mercator_session') || '{}') as Record<string, string>
    expect(storedSession.user_id).toBe('user-123')
    expect(storedSession.session_token).toBe('session-abc')
    expect(storedSession.algo_address).toBe('TESTALGOWALLETADDRESS111111111111111111111111111111111')
  })
})