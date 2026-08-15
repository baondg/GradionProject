import { type FormEvent, useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { identify } from "../api"
import { useAuth } from "../auth"

export function IdentityPage() {
  const { identity, signIn } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  if (identity) return <Navigate to="/projects" replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmedName = name.trim()
    const trimmedEmail = email.trim()
    if (!trimmedName || !trimmedEmail.includes("@")) {
      setError("Enter your name and a valid email to continue.")
      return
    }
    setError("")
    setSubmitting(true)
    try {
      const user = await identify(trimmedName, trimmedEmail)
      signIn(user)
      navigate("/projects")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="logo-row">GRADION</div>
        <h3>Book Illustration Studio</h3>
        <p className="lede">
          Enter your details to start or resume an illustration project.
        </p>
        <label className="gd-field">
          <span>
            Full name <span className="req">*</span>
          </span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Mira Hassan"
            autoComplete="name"
          />
        </label>
        <label className="gd-field">
          <span>
            Email <span className="req">*</span>
          </span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="mira@example.com"
            autoComplete="email"
          />
        </label>
        {error ? <p className="err">{error}</p> : null}
        <button
          className="gd-btn gd-btn-primary"
          type="submit"
          disabled={submitting}
        >
          Continue <span className="gd-arrow">→</span>
        </button>
        <p className="meta hint">
          No password — this is a lightweight identity check. Using an email
          that already has projects resumes them where you left off.
        </p>
      </form>
    </div>
  )
}
