import { useState, useCallback, useEffect } from 'react'
import api from '../api/client'
import type { User } from '../types'
import type { AuthState } from '../stores/authStore'

export function useAuthProvider(): AuthState {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setLoading] = useState(true)

  const logout = useCallback(() => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      api.post('/auth/logout', { refresh_token: refreshToken }).catch(() => {})
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      setLoading(false)
      return
    }
    api
      .get<User>('/auth/me')
      .then(({ data }) => setUser(data))
      .catch(() => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
      })
      .finally(() => setLoading(false))
  }, [])

  return {
    user,
    isAuthenticated: !!user,
    isLoading,
    setUser,
    setLoading,
    logout,
  }
}
