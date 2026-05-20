import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAppContext } from '../context/AppContext'
import { ApiError, api } from '../utils/api'

type ImportedWallet = {
  label: string
  wallet_address: string
  mnemonic: string
  imported_at: string
}

const STORAGE_KEY = 'mercator_imported_wallet'

function maskedMnemonic(mnemonic: string) {
  const words = mnemonic.trim().split(/\s+/).filter(Boolean)
  if (words.length <= 4) return mnemonic.trim()
  return `${words.slice(0, 3).join(' ')} ... ${words.slice(-3).join(' ')}`
}

export default function WalletToolsPage() {
  const { setBuyerWallet } = useAppContext()
  const [checkAddress, setCheckAddress] = useState('')
  const [custodialResult, setCustodialResult] = useState<{
    is_custodial: boolean
    user_id?: string | null
    address?: string
  } | null>(null)
  const [checkingCustodial, setCheckingCustodial] = useState(false)
  const [checkError, setCheckError] = useState<string | null>(null)

  const [exportUserId, setExportUserId] = useState('')
  const [exportPassword, setExportPassword] = useState('')
  const [exportResult, setExportResult] = useState<{ mnemonic: string; warning: string } | null>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const [importLabel, setImportLabel] = useState('Imported buyer wallet')
  const [importWalletAddress, setImportWalletAddress] = useState('')
  const [importMnemonic, setImportMnemonic] = useState('')
  const [importedWallet, setImportedWallet] = useState<ImportedWallet | null>(null)

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as ImportedWallet
      if (parsed?.wallet_address && parsed?.mnemonic) {
        setImportedWallet(parsed)
        setImportLabel(parsed.label || importLabel)
        setImportWalletAddress(parsed.wallet_address)
        setImportMnemonic(parsed.mnemonic)
      }
    } catch {
      // Ignore malformed local data.
    }
  }, [])

  const importedMnemonicPreview = useMemo(() => {
    if (!importedWallet?.mnemonic) return ''
    return maskedMnemonic(importedWallet.mnemonic)
  }, [importedWallet])

  const handleCustodialCheck = async () => {
    const trimmed = checkAddress.trim()
    if (!trimmed) {
      setCheckError('Enter a wallet address to check custody.')
      return
    }

    setCheckingCustodial(true)
    setCheckError(null)
    setCustodialResult(null)
    try {
      const response = await api.walletIsCustodial(trimmed)
      setCustodialResult(response)
      toast.success(response.is_custodial ? 'Custodial wallet found.' : 'Wallet is not custodial.')
    } catch (error) {
      const message = error instanceof ApiError ? error.userMessage : 'Failed to check wallet custody'
      setCheckError(message)
      toast.error(message)
    } finally {
      setCheckingCustodial(false)
    }
  }

  const handleWalletExport = async () => {
    const trimmedUserId = exportUserId.trim()
    const trimmedPassword = exportPassword.trim()
    if (!trimmedUserId || !trimmedPassword) {
      setExportError('Enter a user ID and password to export a custodial wallet.')
      return
    }

    setExportLoading(true)
    setExportError(null)
    setExportResult(null)
    try {
      const response = await api.walletExport(trimmedUserId, trimmedPassword)
      setExportResult(response)
      toast.success('Wallet mnemonic exported.')
    } catch (error) {
      const message = error instanceof ApiError ? error.userMessage : 'Failed to export wallet'
      setExportError(message)
      toast.error(message)
    } finally {
      setExportLoading(false)
    }
  }

  const handleWalletImport = () => {
    const trimmedMnemonic = importMnemonic.trim().replace(/\s+/g, ' ')
    const trimmedWalletAddress = importWalletAddress.trim()
    if (!trimmedMnemonic || !trimmedWalletAddress) {
      toast.error('Provide a wallet address and mnemonic to import locally.')
      return
    }

    const nextWallet: ImportedWallet = {
      label: importLabel.trim() || 'Imported buyer wallet',
      wallet_address: trimmedWalletAddress,
      mnemonic: trimmedMnemonic,
      imported_at: new Date().toISOString(),
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(nextWallet))
    setImportedWallet(nextWallet)
    setBuyerWallet(trimmedWalletAddress)
    toast.success('Wallet imported locally into this browser.')
  }

  const clearImportedWallet = () => {
    localStorage.removeItem(STORAGE_KEY)
    setImportedWallet(null)
    setImportMnemonic('')
    setImportWalletAddress('')
    setImportLabel('Imported buyer wallet')
    toast.success('Imported wallet removed from this browser.')
  }

  return (
    <div className="mercator-themed-page min-h-screen bg-[radial-gradient(1100px_560px_at_0%_0%,rgba(220,176,153,0.22),transparent_58%),radial-gradient(860px_460px_at_100%_0%,rgba(111,57,70,0.14),transparent_54%),linear-gradient(180deg,#fff8f4_0%,#fffdf8_100%)] px-4 py-10 text-slate-900 md:px-6">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6 md:p-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">Wallet Center</p>
              <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950">Check custody, export mnemonics, and import wallets locally.</h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                The export flow talks to the backend, while the import flow stays local to this browser session so you can seed the buyer wallet without exposing anything server-side.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link to="/onboard" className="rounded-full border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950">
                Onboarding
              </Link>
              <Link to="/login" className="rounded-full bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800">
                Login
              </Link>
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-3">
          <article className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Custodial check</p>
            <h2 className="mt-2 text-2xl font-black text-slate-950">Is this wallet custodial?</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Query <span className="font-semibold">GET /wallet/is_custodial</span> with any Algorand address.
            </p>

            <label className="mt-5 block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Wallet address</span>
              <input
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                value={checkAddress}
                onChange={(event) => setCheckAddress(event.target.value)}
                placeholder="Algorand address"
              />
            </label>

            <button
              type="button"
              className="mt-4 w-full rounded-2xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={handleCustodialCheck}
              disabled={checkingCustodial}
            >
              {checkingCustodial ? 'Checking...' : 'Check custody'}
            </button>

            {checkError && <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{checkError}</div>}

            {custodialResult && (
              <div className={`mt-4 rounded-2xl px-4 py-3 text-sm ${custodialResult.is_custodial ? 'border border-emerald-200 bg-emerald-50 text-emerald-800' : 'border border-amber-200 bg-amber-50 text-amber-900'}`}>
                <p className="font-semibold">{custodialResult.is_custodial ? 'Custodial wallet' : 'Self-custodial wallet'}</p>
                <p className="mt-1 break-all">Address: {custodialResult.address}</p>
                {custodialResult.user_id && <p className="mt-1 break-all">User ID: {custodialResult.user_id}</p>}
              </div>
            )}
          </article>

          <article className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Export wallet</p>
            <h2 className="mt-2 text-2xl font-black text-slate-950">Recover the custodial mnemonic</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Export calls the backend <span className="font-semibold">POST /wallet/export</span> endpoint with a user ID and password.
            </p>

            <div className="mt-5 grid gap-4">
              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">User ID</span>
                <input
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={exportUserId}
                  onChange={(event) => setExportUserId(event.target.value)}
                  placeholder="Custodial user id"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Password</span>
                <input
                  type="password"
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={exportPassword}
                  onChange={(event) => setExportPassword(event.target.value)}
                  placeholder="Account password"
                />
              </label>

              <button
                type="button"
                className="rounded-2xl bg-amber-500 px-5 py-3.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={handleWalletExport}
                disabled={exportLoading}
              >
                {exportLoading ? 'Exporting...' : 'Export mnemonic'}
              </button>
            </div>

            {exportError && <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{exportError}</div>}

            {exportResult && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                <p className="font-semibold">Mnemonic exported.</p>
                <p className="mt-2 break-words font-mono text-xs leading-6 text-amber-950">{exportResult.mnemonic}</p>
                <p className="mt-3 text-xs leading-5 text-amber-800">{exportResult.warning}</p>
                <button
                  type="button"
                  className="mt-4 rounded-full bg-slate-950 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(exportResult.mnemonic)
                      toast.success('Mnemonic copied to clipboard.')
                    } catch {
                      toast.error('Could not copy mnemonic.')
                    }
                  }}
                >
                  Copy mnemonic
                </button>
              </div>
            )}
          </article>

          <article className="mercator-elevated-card rounded-3xl border border-slate-200 bg-white p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Import wallet</p>
            <h2 className="mt-2 text-2xl font-black text-slate-950">Import a wallet locally</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Paste a wallet address and mnemonic to keep a local browser copy for buyer flows. This does not send the mnemonic back to the server.
            </p>

            <div className="mt-5 grid gap-4">
              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Label</span>
                <input
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={importLabel}
                  onChange={(event) => setImportLabel(event.target.value)}
                  placeholder="Imported wallet"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Wallet address</span>
                <input
                  className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={importWalletAddress}
                  onChange={(event) => setImportWalletAddress(event.target.value)}
                  placeholder="Algorand address"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Mnemonic</span>
                <textarea
                  className="min-h-32 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:bg-white"
                  value={importMnemonic}
                  onChange={(event) => setImportMnemonic(event.target.value)}
                  placeholder="25-word recovery phrase"
                />
              </label>

              <button
                type="button"
                className="rounded-2xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-slate-800"
                onClick={handleWalletImport}
              >
                Save locally
              </button>

              {importedWallet && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                  <p className="font-semibold text-slate-950">{importedWallet.label}</p>
                  <p className="mt-1 break-all">{importedWallet.wallet_address}</p>
                  <p className="mt-2 font-mono text-xs text-slate-600">{importedMnemonicPreview}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded-full bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
                      onClick={() => {
                        setBuyerWallet(importedWallet.wallet_address)
                        toast.success('Imported wallet set as buyer wallet.')
                      }}
                    >
                      Use as buyer wallet
                    </button>
                    <button
                      type="button"
                      className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                      onClick={clearImportedWallet}
                    >
                      Clear import
                    </button>
                  </div>
                </div>
              )}
            </div>
          </article>
        </section>
      </div>
    </div>
  )
}