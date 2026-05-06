import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import type { ResetPasswordResponse } from '../../types'
import styles from '../Profile/Profile.module.css'

interface Props {
  userId: number
  onClose: () => void
}

function errorMessage(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string') {
    return e.response.data.detail
  }
  return fallback
}

export default function ResetPasswordModal({ userId, onClose }: Props) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ResetPasswordResponse | null>(null)

  const reset = async () => {
    setBusy(true)
    try {
      const { data } = await api.post<ResetPasswordResponse>(
        `/admin/users/${userId}/reset-password`,
        {},
      )
      setResult(data)
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка сброса пароля'))
    } finally {
      setBusy(false)
    }
  }

  const copyPassword = async () => {
    if (!result) return
    try {
      await navigator.clipboard.writeText(result.password)
      toast.success('Скопировано')
    } catch {
      toast.error('Не удалось скопировать')
    }
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {!result ? (
          <>
            <h3>Сбросить пароль?</h3>
            <p>
              Текущие сессии пользователя будут завершены, ему придётся сменить пароль при
              следующем входе.
            </p>
            <div className={styles.modalActions}>
              <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>
                Отмена
              </button>
              <button className={styles.btnPrimary} onClick={reset} disabled={busy}>
                Сбросить
              </button>
            </div>
          </>
        ) : (
          <>
            <h3>Новый пароль для {result.username}</h3>
            <code
              style={{
                padding: '0.5rem',
                background: 'var(--bg-secondary)',
                borderRadius: 4,
                display: 'block',
                wordBreak: 'break-all',
              }}
            >
              {result.password}
            </code>
            <button className={styles.btnSecondary} onClick={copyPassword}>
              Скопировать
            </button>
            <div className={styles.modalActions}>
              <button className={styles.btnPrimary} onClick={onClose}>
                Закрыть
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
