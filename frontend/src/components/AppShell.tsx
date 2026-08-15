import { Link, Outlet, useNavigate } from "react-router-dom"
import { useAuth } from "../auth"

export function AppShell() {
  const { identity, signOut } = useAuth()
  const navigate = useNavigate()
  const initials = (identity?.name ?? "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()

  return (
    <>
      <header className="gd-nav">
        <div className="gd-nav-inner">
          <Link to="/projects" className="gd-nav-logo">
            GRADION
          </Link>
          <nav className="gd-nav-links">
            <Link to="/projects">Projects</Link>
          </nav>
          <div className="gd-nav-user">
            <div className="gd-nav-avatar" aria-hidden="true">
              {initials}
            </div>
            <span>{identity?.name}</span>
            <button
              type="button"
              className="sign-out"
              onClick={() => {
                signOut()
                navigate("/")
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <Outlet />
      <footer className="app-footer">
        <span className="gd-signature">
          GRADION <b>|</b> Scaling Business
        </span>
      </footer>
    </>
  )
}
