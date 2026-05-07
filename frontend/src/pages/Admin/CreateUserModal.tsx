import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { CreateUserResponse, Role } from '../../types'
import styles from '../Profile/Profile.module.css'

interface Props {
  onClose: () => void
  onCreated: () => void
}

const DEFAULT_PERMS = { youtube: true, converter: true, image: true }
const DEFAULT_LIMITS = { youtube_daily: 50, convert_daily: 100, image_daily: 50 }
const USERNAME_RE = /^[a-zA-Z0-9_]{2,50}$/

function errorMessage(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string') {
    return e.response.data.detail
  }
  return fallback
}

export default function CreateUserModal({ onClose, onCreated }: Props) {
  const { user: actor } = useAuth()
  const isSuperadmin = actor?.role === 'superadmin'
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<Role>('user')
  const [perms, setPerms] = useState({ ...DEFAULT_PERMS })
  const [limits, setLimits] = useState({ ...DEFAULT_LIMITS })
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState<CreateUserResponse | null>(null)

  const submit = async () => {
    if (!USERNAME_RE.test(username)) {
      toast.error('Имя: 2–50 символов, только буквы/цифры/подчёркивание')
      return
    }
    setBusy(true)
    try {
      const { data } = await api.post<CreateUserResponse>('/admin/users', {
        username,
        role,
        permissions: perms,
        limits,
      })
      setCreated(data)
      onCreated()
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка создания пользователя'))
    } finally {
      setBusy(false)
    }
  }

  const copyPassword = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.password)
      toast.success('Скопировано')
    } catch {
      toast.error('Не удалось скопировать')
    }
  }

  if (created) {
    return (
      <div className={styles.modalOverlay} onClick={onClose}>
        <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
          <h3>Пользователь создан</h3>
          <p>Имя: <strong>{created.username}</strong></p>
          <p>Пароль (показывается один раз):</p>
          <code style={{ padding: '0.5rem', background: 'var(--bg-secondary)', borderRadius: 4, display: 'block', wordBreak: 'break-all' }}>
            {created.password}
          </code>
          <button className={styles.btnSecondary} onClick={copyPassword}>Скопировать</button>
          <div className={styles.modalActions}>
            <button className={styles.btnPrimary} onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        style={{ width: 'min(92vw, 520px)' }}
      >
        <h3>Создание пользователя</h3>
        <input
          className={styles.input}
          placeholder="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <label>
          Роль:{' '}
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="user">user</option>
            {isSuperadmin && <option value="admin">admin</option>}
            {isSuperadmin && <option value="superadmin">superadmin</option>}
          </select>
        </label>
        <fieldset>
          <legend>Права</legend>
          {(['youtube', 'converter', 'image'] as const).map((k) => (
            <label key={k} style={{ display: 'block' }}>
              <input
                type="checkbox"
                checked={perms[k]}
                onChange={(e) => setPerms({ ...perms, [k]: e.target.checked })}
              />{' '}
              {k}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Лимиты</legend>
          {(
            [
              ['youtube_daily', 'YouTube'],
              ['convert_daily', 'Convert'],
              ['image_daily', 'Image'],
            ] as const
          ).map(([k, l]) => (
            <label key={k} style={{ display: 'block' }}>
              {l}:{' '}
              <input
                type="number"
                min={0}
                value={limits[k]}
                onChange={(e) => setLimits({ ...limits, [k]: Number(e.target.value) })}
              />
            </label>
          ))}
        </fieldset>
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button className={styles.btnPrimary} onClick={submit} disabled={busy}>
            Создать
          </button>
        </div>
      </div>
    </div>
  )
}
