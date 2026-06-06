import { useState } from 'react'
import { extractApiError } from '../../utils/apiError'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import { Button, Input } from '../../components/ui'
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
      toast.error(extractApiError(e, 'Ошибка'))
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
        Изменить имя
      </Button>
    )
  }

  return (
    <div className={styles.inlineForm}>
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
        autoFocus
      />
      <Button variant="primary" size="sm" onClick={submit} disabled={busy} loading={busy}>
        Сохранить
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          setEditing(false)
          setValue(user.username)
        }}
        disabled={busy}
      >
        Отмена
      </Button>
    </div>
  )
}
