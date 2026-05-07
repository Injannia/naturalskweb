import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import styles from '../Profile/Profile.module.css'

interface Props {
  userId: number
  username: string
  onClose: () => void
  onDeleted: () => void
}

function errorMessage(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string') {
    return e.response.data.detail
  }
  return fallback
}

export default function ConfirmDeleteModal({ userId, username, onClose, onDeleted }: Props) {
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    if (confirm !== username) {
      toast.error('Имя не совпадает')
      return
    }
    setBusy(true)
    try {
      await api.delete(`/admin/users/${userId}`)
      toast.success('Пользователь удалён')
      onDeleted()
      onClose()
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка удаления'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Удалить пользователя {username}?</h3>
        <p>Введите username для подтверждения:</p>
        <input
          className={styles.input}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            className={styles.btnDanger}
            onClick={remove}
            disabled={busy || confirm !== username}
          >
            Удалить
          </button>
        </div>
      </div>
    </div>
  )
}
