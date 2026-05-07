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

  // Background poll: catch admin-side permission/role/active changes within ~15s.
  // Skip while the tab is hidden so we don't burn requests on inactive tabs;
  // 401 from kicked_at/is_deleted is handled by the axios interceptor.
  useEffect(() => {
    if (!user) return
    const POLL_MS = 15_000
    let stopped = false

    const tick = async () => {
      if (stopped) return
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      try {
        const { data } = await api.get<User>('/auth/me')
        if (!stopped) setUser(data)
      } catch {
        // axios interceptor handles 401 (forced logout)
      }
    }

    const id = window.setInterval(tick, POLL_MS)
    return () => {
      stopped = true
      window.clearInterval(id)
    }
  }, [user?.id])

  return {
    user,
    isAuthenticated: !!user,
    isLoading,
    setUser,
    setLoading,
    logout,
  }
}
