import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
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
      setOpen(false)
      reset()
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
      <button className={styles.btnSecondary} onClick={() => setOpen(true)}>
        Сменить пароль
      </button>
    )
  }

  return (
    <div
      className={styles.modalOverlay}
      onClick={() => {
        if (!busy) {
          setOpen(false)
          reset()
        }
      }}
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Смена пароля</h3>
        <input
          className={styles.input}
          type="password"
          placeholder="Текущий пароль"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          disabled={busy}
        />
        <input
          className={styles.input}
          type="password"
          placeholder="Новый пароль (мин. 8)"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          disabled={busy}
        />
        <input
          className={styles.input}
          type="password"
          placeholder="Повторите новый"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          disabled={busy}
        />
        <div className={styles.modalActions}>
          <button
            className={styles.btnSecondary}
            onClick={() => {
              setOpen(false)
              reset()
            }}
            disabled={busy}
          >
            Отмена
          </button>
          <button className={styles.btnPrimary} onClick={submit} disabled={busy}>
            Сменить
          </button>
        </div>
      </div>
    </div>
  )
}
