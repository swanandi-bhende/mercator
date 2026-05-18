import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import WalletToolsPage from './WalletTools'

const setBuyerWalletMock = vi.fn()
const walletIsCustodialMock = vi.fn()
const walletExportMock = vi.fn()

vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({
    setBuyerWallet: setBuyerWalletMock,
  }),
}))

vi.mock('../utils/api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    walletIsCustodial: (...args: unknown[]) => walletIsCustodialMock(...args),
    walletExport: (...args: unknown[]) => walletExportMock(...args),
  },
}))

describe('WalletToolsPage', () => {
  beforeEach(() => {
    setBuyerWalletMock.mockReset()
    walletIsCustodialMock.mockReset()
    walletExportMock.mockReset()
    localStorage.clear()
  })

  it('checks custody and exports a wallet mnemonic', async () => {
    walletIsCustodialMock.mockResolvedValue({
      is_custodial: true,
      user_id: 'user-555',
      address: 'TESTALGOWALLETADDRESS111111111111111111111111111111111',
    })
    walletExportMock.mockResolvedValue({
      mnemonic: 'word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24 word25',
      warning: 'Store this mnemonic securely.',
    })

    render(
      <MemoryRouter>
        <WalletToolsPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getAllByPlaceholderText(/algorand address/i)[0], {
      target: { value: 'TESTALGOWALLETADDRESS111111111111111111111111111111111' },
    })
    fireEvent.click(screen.getByRole('button', { name: /check custody/i }))

    expect(await screen.findByText(/custodial wallet/i)).toBeInTheDocument()
    expect(screen.getByText(/user-555/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^user id$/i), { target: { value: 'user-555' } })
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'wallet-password' } })
    fireEvent.click(screen.getByRole('button', { name: /export mnemonic/i }))

    expect(await screen.findByText(/mnemonic exported/i)).toBeInTheDocument()
    expect(screen.getByText(/word1 word2 word3/i)).toBeInTheDocument()
  })
})