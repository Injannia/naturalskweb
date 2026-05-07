import { useEffect, useState } from 'react'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { Role, UpdateUserRequest, UserDetail } from '../../types'
import styles from '../Profile/Profile.module.css'

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
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        style={{ width: 'min(92vw, 520px)' }}
      >
        <h3>
          {editable ? 'Редактирование' : 'Подробно'}: {user.username}
        </h3>

        {editable && actor.role === 'superadmin' && (
          <label>
            Роль:{' '}
            <select
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
              <option value="superadmin">superadmin</option>
            </select>
          </label>
        )}
        <fieldset>
          <legend>Права</legend>
          {(['youtube', 'converter', 'image'] as const).map((k) => (
            <label key={k} style={{ display: 'block' }}>
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
                disabled={!editable}
                value={draft.limits?.[k] ?? 0}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    limits: { ...draft.limits, [k]: Number(e.target.value) },
                  })
                }
              />
            </label>
          ))}
        </fieldset>
        {editable && (
          <label>
            <input
              type="checkbox"
              checked={!!draft.is_active}
              onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
            />{' '}
            Активен
          </label>
        )}
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>
            Закрыть
          </button>
          {editable && (
            <button className={styles.btnPrimary} onClick={save} disabled={busy}>
              Сохранить
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
