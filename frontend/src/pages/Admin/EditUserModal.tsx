import { useEffect, useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import { Button, Input } from '../../components/ui'
import type { Role, UpdateUserRequest, UserDetail } from '../../types'
import styles from './Admin.module.css'

interface Props {
  userId: number
  onClose: () => void
  onSaved: () => void
}

function canModify(actorRole: string, actorId: number, target: UserDetail): boolean {
  if (actorRole === 'superadmin') return true
  if (actorRole !== 'admin') return false
  if (target.role === 'superadmin') return false
  if (target.id === actorId) return false
  return true
}

function errorMessage(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string') {
    return e.response.data.detail
  }
  return fallback
}

export default function EditUserModal({ userId, onClose, onSaved }: Props) {
  const { user: actor } = useAuth()
  const [user, setUser] = useState<UserDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<UpdateUserRequest>({})

  useEffect(() => {
    api
      .get<UserDetail>(`/admin/users/${userId}`)
      .then(({ data }) => {
        setUser(data)
        setDraft({
          role: data.role as Role,
          permissions: { ...data.permissions },
          limits: { ...data.limits },
          is_active: data.is_active,
        })
      })
      .catch((e: unknown) => {
        toast.error(errorMessage(e, 'Ошибка загрузки пользователя'))
      })
  }, [userId])

  if (!user || !actor) return null
  const editable = canModify(actor.role, actor.id, user)
  // Limits are editable only by a superadmin and only for regular users.
  const canEditLimits = actor.role === 'superadmin' && user.role === 'user'

  const save = async () => {
    setBusy(true)
    try {
      await api.patch(`/admin/users/${userId}`, draft)
      toast.success('Сохранено')
      onSaved()
      onClose()
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка сохранения'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.modalBackdrop} onClick={() => !busy && onClose()}>
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 'min(92vw, 520px)' }}
      >
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>
            {editable ? 'Редактирование' : 'Подробно'}: {user.username}
          </h3>
        </div>

        <div className={styles.modalForm}>
          {editable && actor.role === 'superadmin' && (
            <label>
              <span style={{ display: 'block', fontSize: 'var(--fs-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                Роль
              </span>
              <select
                value={draft.role}
                onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}
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
                <option value="admin">admin</option>
                <option value="superadmin">superadmin</option>
              </select>
            </label>
          )}

          <fieldset style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-4)' }}>
            <legend style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', padding: '0 var(--space-2)' }}>
              Права
            </legend>
            {(['youtube', 'converter', 'image'] as const).map((k) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', padding: 'var(--space-1) 0', color: 'var(--text-primary)' }}>
                <input
                  type="checkbox"
                  disabled={!editable}
                  checked={!!draft.permissions?.[k]}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      permissions: { ...draft.permissions, [k]: e.target.checked },
                    })
                  }
                  style={{ accentColor: 'var(--accent-1)' }}
                />
                {k}
              </label>
            ))}
          </fieldset>

          {canEditLimits && (
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
                  ] as const
                ).map(([k, l]) => (
                  <Input
                    key={k}
                    label={l}
                    type="number"
                    min={0}
                    value={draft.limits?.[k] ?? 0}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        limits: { ...draft.limits, [k]: Number(e.target.value) },
                      })
                    }
                  />
                ))}
              </div>
            </fieldset>
          )}

          {editable && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'var(--text-primary)' }}>
              <input
                type="checkbox"
                checked={!!draft.is_active}
                onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                style={{ accentColor: 'var(--accent-1)' }}
              />
              Активен
            </label>
          )}
        </div>

        <div className={styles.modalActions}>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Закрыть
          </Button>
          {editable && (
            <Button variant="primary" onClick={save} disabled={busy} loading={busy}>
              Сохранить
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
