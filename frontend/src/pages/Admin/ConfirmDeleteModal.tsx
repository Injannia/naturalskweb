import { useState } from 'react'
import { extractApiError as errorMessage } from '../../utils/apiError'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { Button, Input } from '../../components/ui'
import styles from './Admin.module.css'

interface Props {
  userId: number
  username: string
  onClose: () => void
  onDeleted: () => void
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
    <div className={styles.modalBackdrop} onClick={() => !busy && onClose()}>
      <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Удалить пользователя {username}?</h3>
        </div>
        <div className={styles.modalForm}>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>
            Введите username для подтверждения:
          </p>
          <Input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoFocus
          />
        </div>
        <div className={styles.modalActions}>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Отмена
          </Button>
          <Button
            variant="danger"
            onClick={remove}
            disabled={busy || confirm !== username}
            loading={busy}
          >
            Удалить
          </Button>
        </div>
      </div>
    </div>
  )
}
