import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { Button } from '../../components/ui'
import type { ResetPasswordResponse } from '../../types'
import styles from './Admin.module.css'

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
    <div className={styles.modalBackdrop} onClick={() => !busy && onClose()}>
      <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
        {!result ? (
          <>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Сбросить пароль?</h3>
            </div>
            <div className={styles.modalForm}>
              <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', lineHeight: 1.5 }}>
                Текущие сессии пользователя будут завершены, ему придётся сменить пароль при
                следующем входе.
              </p>
            </div>
            <div className={styles.modalActions}>
              <Button variant="ghost" onClick={onClose} disabled={busy}>
                Отмена
              </Button>
              <Button variant="primary" onClick={reset} disabled={busy} loading={busy}>
                Сбросить
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Новый пароль для {result.username}</h3>
            </div>
            <div className={styles.modalForm}>
              <code
                style={{
                  padding: 'var(--space-3)',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  display: 'block',
                  wordBreak: 'break-all',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {result.password}
              </code>
              <Button variant="secondary" size="sm" onClick={copyPassword}>
                Скопировать
              </Button>
            </div>
            <div className={styles.modalActions}>
              <Button variant="primary" onClick={onClose}>Закрыть</Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
