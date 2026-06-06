import { useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import { Button, Input } from '../../components/ui'
import type { CreateUserResponse, Role } from '../../types'
import styles from './Admin.module.css'

interface Props {
  onClose: () => void
  onCreated: () => void
}

const DEFAULT_PERMS = { youtube: true, converter: true, image: true, multidl: true }
const DEFAULT_LIMITS = { youtube_daily: 50, convert_daily: 100, image_daily: 50, multidl_daily: 50 }
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
        // Limits only matter for regular users; admins/superadmins are unlimited.
        ...(role === 'user' ? { limits } : {}),
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
      <div className={styles.modalBackdrop} onClick={onClose}>
        <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
          <div className={styles.modalHeader}>
            <h3 className={styles.modalTitle}>Пользователь создан</h3>
          </div>
          <div className={styles.modalForm}>
            <p>Имя: <strong>{created.username}</strong></p>
            <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>
              Пароль (показывается один раз):
            </p>
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
              {created.password}
            </code>
            <Button variant="secondary" size="sm" onClick={copyPassword}>
              Скопировать
            </Button>
          </div>
          <div className={styles.modalActions}>
            <Button variant="primary" onClick={onClose}>Закрыть</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.modalBackdrop} onClick={() => !busy && onClose()}>
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 'min(92vw, 520px)' }}
      >
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Создание пользователя</h3>
        </div>

        <div className={styles.modalForm}>
          <Input
            label="Username"
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />

          <label>
            <span style={{ display: 'block', fontSize: 'var(--fs-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Роль
            </span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              style={{
                width: '100%',
                padding: 'var(--space-3) var(--space-4)',
                background: 'var(--bg-input)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-ui)',
                fontSize: 'var(--fs-base)',
                minHeight: 44,
              }}
            >
              <option value="user">user</option>
              {isSuperadmin && <option value="admin">admin</option>}
              {isSuperadmin && <option value="superadmin">superadmin</option>}
            </select>
          </label>

          <fieldset style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-4)' }}>
            <legend style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', padding: '0 var(--space-2)' }}>
              Права
            </legend>
            {(['youtube', 'converter', 'image', 'multidl'] as const).map((k) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', padding: 'var(--space-1) 0', color: 'var(--text-primary)' }}>
                <input
                  type="checkbox"
                  checked={perms[k]}
                  onChange={(e) => setPerms({ ...perms, [k]: e.target.checked })}
                  style={{ accentColor: 'var(--accent-1)' }}
                />
                {k}
              </label>
            ))}
          </fieldset>

          {role === 'user' && (
            <fieldset style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-4)' }}>
              <legend style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', padding: '0 var(--space-2)' }}>
                Лимиты
              </legend>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {(
                  [
                    ['youtube_daily', 'YouTube'],
                    ['convert_daily', 'Convert'],
                    ['image_daily', 'Image'],
                    ['multidl_daily', 'Multi downloader'],
                  ] as const
                ).map(([k, l]) => (
                  <Input
                    key={k}
                    label={l}
                    type="number"
                    min={0}
                    value={limits[k]}
                    onChange={(e) => setLimits({ ...limits, [k]: Number(e.target.value) })}
                  />
                ))}
              </div>
            </fieldset>
          )}

        </div>

        <div className={styles.modalActions}>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Отмена
          </Button>
          <Button variant="primary" onClick={submit} disabled={busy} loading={busy}>
            Создать
          </Button>
        </div>
      </div>
    </div>
  )
}
