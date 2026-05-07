import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Loader2 } from 'lucide-react'
import { login, register } from '../api/auth'
import { useAuthStore } from '../store/useAuthStore'
import clsx from 'clsx'

type Tab = 'login' | 'register'

export default function AuthPage() {
  const [tab, setTab] = useState<Tab>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const setTokens = useAuthStore((s) => s.setTokens)
  const setEmailStore = useAuthStore((s) => s.setEmail)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setLoading(true)

    try {
      if (tab === 'register') {
        await register(email, password)
        setSuccess('Account created! Logging you in…')
        const tokens = await login(email, password)
        setTokens(tokens.access_token, tokens.refresh_token, email)
        setEmailStore(email)
        navigate('/', { replace: true })
      } else {
        const tokens = await login(email, password)
        setTokens(tokens.access_token, tokens.refresh_token, email)
        setEmailStore(email)
        navigate('/', { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl mb-4 shadow-lg">
            <MessageSquare className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">RAG Chat</h1>
          <p className="text-gray-500 text-sm mt-1">Chat with your documents</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-gray-100">
            {(['login', 'register'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError(null); setSuccess(null) }}
                className={clsx(
                  'flex-1 py-3.5 text-sm font-semibold transition-colors',
                  tab === t
                    ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                    : 'text-gray-500 hover:text-gray-700',
                )}
              >
                {t === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-8 space-y-5">
            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 border border-red-100">
                {error}
              </div>
            )}
            {success && (
              <div className="bg-green-50 text-green-700 text-sm rounded-lg px-4 py-3 border border-green-100">
                {success}
              </div>
            )}

            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                minLength={6}
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-semibold py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2 text-sm shadow-sm"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {tab === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
