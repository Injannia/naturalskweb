import { createContext, useContext } from 'react'
import type { User } from '../types'

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  setUser: (user: User | null) => void
  setLoading: (loading: boolean) => void
  logout: () => void
}

export const AuthContext = createContext<AuthState>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  setUser: () => {},
  setLoading: () => {},
  logout: () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}
