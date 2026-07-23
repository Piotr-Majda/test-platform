import { useState, type FormEvent } from 'react'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { login, loginAsGuest } = useAuth()
  const [username, setUsername] = useState('viewer')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  const openGuestDemo = async () => {
    setBusy(true)
    setError(null)
    try {
      await loginAsGuest()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open guest demo')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <p className="login-eyebrow">TEST AUTOMATION · LIVE DEMO</p>
        <h1 id="login-title">Test Platform</h1>
        <p className="login-copy">
          Explore test runs, logs, artifacts and AI-assisted failure analysis.
        </p>
        <form onSubmit={(event) => void submit(event)}>
          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoFocus
            />
          </label>
          {error ? <p className="error" role="alert">{error}</p> : null}
          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Open demo'}
          </button>
          <button
            className="ghost login-submit login-guest"
            type="button"
            disabled={busy}
            onClick={() => void openGuestDemo()}
          >
            {busy ? 'Opening demo…' : 'Explore as guest'}
          </button>
        </form>
        <p className="login-note">
          Guest access is read-only. Running tests, AI analysis and configuration changes are
          disabled.
        </p>
      </section>
    </main>
  )
}
