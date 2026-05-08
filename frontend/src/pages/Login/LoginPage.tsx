import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react'
import axios from 'axios'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import AuroraBackground from '../../components/AuroraBackground/AuroraBackground'
import StarryBackground from '../../components/StarryBackground/StarryBackground'
import type { TokenResponse, User as UserType } from '../../types'
import styles from './LoginPage.module.css'

export default function LoginPage() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) return

    setError('')
    setLoading(true)

    try {
      const { data } = await axios.post<TokenResponse>('/api/auth/login', {
        username: username.trim(),
        password,
      })

      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)

      const { data: user } = await api.get<UserType>('/auth/me')
      setUser(user)

      if (data.must_change_password) {
        navigate('/change-password', { replace: true })
      } else {
        navigate('/', { replace: true })
      }
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response) {
        const status = err.response.status
        const detail = err.response.data?.detail

        if (status === 423) {
          const seconds = err.response.data?.remaining_seconds
          const minutes = seconds ? Math.ceil(seconds / 60) : 15
          setError(`Аккаунт заблокирован. Попробуйте через ${minutes} мин.`)
        } else if (status === 401) {
          setError(detail || 'Неверный логин или пароль')
        } else if (status === 429) {
          setError('Слишком много попыток. Подождите немного.')
        } else {
          setError('Ошибка сервера. Попробуйте позже.')
        }
      } else {
        setError('Нет связи с сервером')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <AuroraBackground />
      <StarryBackground />
      <div className={styles.container}>
        <div className={styles.card}>
          <div className={styles.logo}>
            <div className={styles.logoTitle}>
              Naturalsk<span className={styles.logoAccent}>Web</span>
            </div>
            <div className={styles.logoSub}>Command Center</div>
          </div>

          {error && (
            <div className={styles.error}>
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.field}>
              <label className={styles.label}>Имя пользователя</label>
              <div className={styles.inputWrapper}>
                <User className={styles.inputIcon} />
                <input
                  className={styles.input}
                  type="text"
                  placeholder="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                />
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Пароль</label>
              <div className={styles.inputWrapper}>
                <Lock className={styles.inputIcon} />
                <input
                  className={styles.input}
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className={styles.togglePassword}
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={loading || !username.trim() || !password}
            >
              {loading ? <div className={styles.spinner} /> : 'Войти'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}
