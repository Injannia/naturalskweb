import { useEffect, useState, useCallback } from 'react'
import { Plus, Eye, Pencil, Key, Power, Trash2 } from 'lucide-react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { useAuth } from '../../stores/authStore'
import type { Role, UserListItem, UserListResponse } from '../../types'
import styles from './Admin.module.css'

const PAGE_SIZE = 20

type StatusFilter = '' | 'active' | 'inactive' | 'deleted'

function statusOf(u: UserListItem): { label: string; cls: string } {
  if (u.is_deleted) return { label: 'удалён', cls: styles.statusDeleted }
  if (!u.is_active) return { label: 'отключён', cls: styles.statusInactive }
  return { label: 'активен', cls: styles.statusActive }
}

function roleClass(role: string): string {
  if (role === 'superadmin') return styles.roleSuperadmin
  if (role === 'admin') return styles.roleAdmin
  return styles.roleUser
}

function compactUsage(u: UserListItem): string {
  return `Y ${u.usage_today.youtube ?? 0}/${u.limits.youtube_daily ?? 0} · C ${u.usage_today.converter ?? 0}/${u.limits.convert_daily ?? 0} · I ${u.usage_today.image ?? 0}/${u.limits.image_daily ?? 0}`
}

interface Props {
  onCreate: () => void
  onEdit: (id: number) => void
  onResetPassword: (id: number) => void
  onToggle: (id: number) => void
  onDelete: (id: number) => void
}

export default function UsersTab({ onCreate, onEdit, onResetPassword, onToggle, onDelete }: Props) {
  const { user: actor } = useAuth()
  const isSuperadmin = actor?.role === 'superadmin'
  const [items, setItems] = useState<UserListItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [status, setStatus] = useState<StatusFilter>('')

  const load = useCallback(() => {
    const params = new URLSearchParams()
    params.set('offset', String(offset))
    params.set('limit', String(PAGE_SIZE))
    if (search) params.set('search', search)
    if (role) params.set('role', role)
    if (status) params.set('status', status)
    if (status === 'deleted' && isSuperadmin) params.set('include_deleted', 'true')
    api.get<UserListResponse>(`/admin/users?${params}`).then(({ data }) => {
      setItems(data.items)
      setTotal(data.total)
    })
  }, [offset, search, role, status, isSuperadmin])

  useEffect(() => {
    const t = setTimeout(load, search ? 250 : 0)
    return () => clearTimeout(t)
  }, [load, search])

  const canDelete = (u: UserListItem) => isSuperadmin && u.id !== actor?.id && !u.is_deleted
  const canEdit = (u: UserListItem) => {
    if (u.is_deleted) return false
    if (actor?.role === 'admin' && u.role === 'superadmin') return false
    if (actor?.id === u.id) return false
    return true
  }
  const canResetPassword = canEdit
  const canToggle = canEdit

  return (
    <div>
      <div className={styles.toolbar}>
        <input
          placeholder="Поиск по имени"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
        />
        <select
          value={role}
          onChange={(e) => { setRole(e.target.value as Role | ''); setOffset(0) }}
        >
          <option value="">Все роли</option>
          <option value="user">user</option>
          <option value="admin">admin</option>
          <option value="superadmin">superadmin</option>
        </select>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value as StatusFilter); setOffset(0) }}
        >
          <option value="">Все статусы</option>
          <option value="active">Активные</option>
          <option value="inactive">Отключённые</option>
          {isSuperadmin && <option value="deleted">Удалённые</option>}
        </select>
        <div className={styles.toolbarSpacer} />
        <button className={styles.iconBtn} onClick={onCreate}>
          <Plus size={16} /> Создать
        </button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th></th>
            <th>Username</th>
            <th>Роль</th>
            <th>Статус</th>
            <th>Создан</th>
            <th>Последний вход</th>
            <th>Использование</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => {
            const st = statusOf(u)
            return (
              <tr key={u.id}>
                <td><AvatarImage userId={u.id} version={u.avatar_version} size={28} /></td>
                <td>{u.username}</td>
                <td><span className={`${styles.roleBadge} ${roleClass(u.role)}`}>{u.role}</span></td>
                <td><span className={`${styles.statusBadge} ${st.cls}`}>{st.label}</span></td>
                <td>{new Date(u.created_at).toLocaleDateString('ru-RU')}</td>
                <td>{u.last_login ? new Date(u.last_login).toLocaleDateString('ru-RU') : '—'}</td>
                <td className={styles.usageCompact}>{compactUsage(u)}</td>
                <td>
                  <div className={styles.actions}>
                    {!canEdit(u) ? (
                      <button className={styles.iconBtn} onClick={() => onEdit(u.id)} title="Подробно">
                        <Eye size={14} />
                      </button>
                    ) : (
                      <>
                        <button className={styles.iconBtn} onClick={() => onEdit(u.id)} title="Редактировать">
                          <Pencil size={14} />
                        </button>
                        <button
                          className={styles.iconBtn}
                          onClick={() => onResetPassword(u.id)}
                          disabled={!canResetPassword(u)}
                          title="Сбросить пароль"
                        >
                          <Key size={14} />
                        </button>
                        <button
                          className={styles.iconBtn}
                          onClick={() => onToggle(u.id)}
                          disabled={!canToggle(u)}
                          title="Включить/Выключить"
                        >
                          <Power size={14} />
                        </button>
                      </>
                    )}
                    {canDelete(u) && (
                      <button className={styles.iconBtn} onClick={() => onDelete(u.id)} title="Удалить">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className={styles.pagination}>
        <span className={styles.pageInfo}>
          {total === 0 ? '0' : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`} из {total}
        </span>
        <button
          className={styles.iconBtn}
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Назад
        </button>
        <button
          className={styles.iconBtn}
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Вперёд
        </button>
      </div>
    </div>
  )
}
