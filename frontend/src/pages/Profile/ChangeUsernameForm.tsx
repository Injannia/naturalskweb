import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { User } from '../../types'
import styles from './Profile.module.css'

export default function ChangeUsernameForm() {
  const { user, setUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(user?.username ?? '')
  const [busy, setBusy] = useState(false)

  if (!user) return null

  const submit = async () => {
    if (!/^[a-zA-Z0-9_]{2,50}$/.test(value)) {
      toast.error('Имя: 2–50 символов, латиница/цифры/_')
      return
    }
    setBusy(true)
    try {
      const { data } = await api.patch<User>('/me', { username: value })
      setUser(data)
      toast.success('Имя обновлено')
      setEditing(false)
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

  if (!editing) {
    return (
      <button className={styles.btnSecondary} onClick={() => setEditing(true)}>
        Изменить имя
      </button>
    )
  }

  return (
    <div className={styles.inlineForm}>
      <input
        className={styles.input}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
      />
      <button className={styles.btnPrimary} onClick={submit} disabled={busy}>
        Сохранить
      </button>
      <button
        className={styles.btnSecondary}
        onClick={() => {
          setEditing(false)
          setValue(user.username)
        }}
        disabled={busy}
      >
        Отмена
      </button>
    </div>
  )
}
