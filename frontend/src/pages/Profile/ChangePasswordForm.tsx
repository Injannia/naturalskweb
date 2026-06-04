import { useState } from 'react'
import { createPortal } from 'react-dom'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { Button, Input } from '../../components/ui'
import styles from './Profile.module.css'

export default function ChangePasswordForm() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setCurrent('')
    setNext('')
    setConfirm('')
  }

  const close = () => {
    setOpen(false)
    reset()
  }

  const submit = async () => {
    if (next.length < 8) {
      toast.error('Минимум 8 символов')
      return
    }
    if (next !== confirm) {
      toast.error('Пароли не совпадают')
      return
    }
    setBusy(true)
    try {
      await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      toast.success('Пароль изменён')
      close()
    } catch (e: unknown) {
      const detail =
        axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string'
          ? e.response.data.detail
          : 'Ошибка'
      toast.error(detail)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        Сменить пароль
      </Button>
    )
  }

  // Rendered into document.body: the form lives inside a glass <Card> whose
  // backdrop-filter establishes a containing block for position:fixed, which
  // pinned the overlay to the card box instead of the viewport (off-center,
  // partial backdrop). A portal escapes that ancestor.
  return createPortal(
    <div className={styles.modalOverlay} onClick={() => !busy && close()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Смена пароля</h3>
        <Input
          type="password"
          placeholder="Текущий пароль"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          disabled={busy}
        />
        <Input
          type="password"
          placeholder="Новый пароль (мин. 8)"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          disabled={busy}
        />
        <Input
          type="password"
          placeholder="Повторите новый"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          disabled={busy}
        />
        <div className={styles.modalActions}>
          <Button variant="ghost" onClick={close} disabled={busy}>
            Отмена
          </Button>
          <Button variant="primary" onClick={submit} disabled={busy} loading={busy}>
            Сменить
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
