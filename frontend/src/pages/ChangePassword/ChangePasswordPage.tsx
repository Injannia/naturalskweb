import { useState, useMemo, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import AuroraBackground from '../../components/AuroraBackground/AuroraBackground'
import StarryBackground from '../../components/StarryBackground/StarryBackground'
import styles from './ChangePasswordPage.module.css'

function getStrength(password: string): number {
  let score = 0
  if (password.length >= 8) score++
  if (/[a-zA-Z]/.test(password) && /\d/.test(password)) score++
  if (password.length >= 12) score++
  if (/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(password)) score++
  return Math.min(score, 4)
}

export default function ChangePasswordPage() {
  const navigate = useNavigate()
  const { user, setUser } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const strength = useMemo(() => getStrength(newPassword), [newPassword])
  const passwordsMatch = confirmPassword === '' || newPassword === confirmPassword
  const hasLetter = /[a-zA-Z]/.test(newPassword)
  const hasDigit = /\d/.test(newPassword)
  const isValid =
    currentPassword &&
    newPassword.length >= 8 &&
    hasLetter &&
    hasDigit &&
    newPassword === confirmPassword

  const strengthLabels = ['', 'Слабый', 'Средний', 'Хороший', 'Сильный']
  const strengthClasses = [
    '',
    styles.strengthLabelWeak,
    styles.strengthLabelMedium,
    styles.strengthLabelMedium,
    styles.strengthLabelStrong,
  ]

  function getSegmentClass(index: number) {
    if (index >= strength) return ''
    if (strength <= 1) return styles.strengthWeak
    if (strength <= 2) return styles.strengthMedium
    return styles.strengthStrong
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!isValid) return

    setError('')
    setLoading(true)

    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })

      // Optimistic update: don't re-fetch /auth/me — we know the only field
      // that changed is must_change_password. Re-fetching here introduced a
      // race with React's batched state/navigation that sometimes left
      // ProtectedRoute reading must_change_password=true and bouncing the
      // user back to /change-password.
      if (user) setUser({ ...user, must_change_password: false })

      toast.success('Пароль успешно изменён')
      navigate('/', { replace: true })
    } catch (err: unknown) {
      if (
        typeof err === 'object' &&
        err !== null &&
        'response' in err &&
        typeof (err as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
      ) {
        setError((err as { response: { data: { detail: string } } }).response.data.detail)
      } else {
        setError('Ошибка при смене пароля')
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
          <h1 className={styles.title}>Смена пароля</h1>
          <p className={styles.subtitle}>
            Необходимо сменить пароль перед первым использованием. Минимум 8
            символов, буквы и цифры.
          </p>

          {error && <div className={styles.error}>{error}</div>}

          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.field}>
              <label className={styles.label}>Текущий пароль</label>
              <input
                className={styles.input}
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Новый пароль</label>
              <input
                className={styles.input}
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="Мин. 8 символов, буквы + цифры"
              />
              {newPassword && (
                <>
                  <div className={styles.strengthBar}>
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className={`${styles.strengthSegment} ${getSegmentClass(i)}`}
                      />
                    ))}
                  </div>
                  <span
                    className={`${styles.strengthLabel} ${strengthClasses[strength]}`}
                  >
                    {strengthLabels[strength]}
                  </span>
                </>
              )}
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Подтверждение пароля</label>
              <input
                className={styles.input}
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
              />
              {!passwordsMatch && (
                <span className={styles.mismatch}>Пароли не совпадают</span>
              )}
            </div>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={!isValid || loading}
            >
              {loading ? 'Сохранение...' : 'Сменить пароль'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}
