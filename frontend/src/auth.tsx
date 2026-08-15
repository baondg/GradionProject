import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { AUTH_STORAGE_KEY } from "./types"

export type Identity = { email: string; name: string }

type AuthValue = {
  identity: Identity | null
  headers: Record<string, string>
  signIn: (identity: Identity) => void
  signOut: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

function readStored(): Identity | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Identity
    if (parsed.email && parsed.name) return parsed
  } catch {
    /* ignore bad JSON */
  }
  return null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(readStored)

  const signIn = useCallback((next: Identity) => {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next))
    setIdentity(next)
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    setIdentity(null)
  }, [])

  const headers = useMemo((): Record<string, string> => {
    if (!identity) return {}
    return { "X-User-Email": identity.email }
  }, [identity])

  const value = useMemo(
    () => ({ identity, headers, signIn, signOut }),
    [identity, headers, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}
