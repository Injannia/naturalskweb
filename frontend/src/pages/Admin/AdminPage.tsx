import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { extractApiError as errorMessage } from '../../utils/apiError'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import ProfileTab from '../Profile/ProfileTab'
import UsersTab from './UsersTab'
import CreateUserModal from './CreateUserModal'
import EditUserModal from './EditUserModal'
import ResetPasswordModal from './ResetPasswordModal'
import ConfirmDeleteModal from './ConfirmDeleteModal'
import AuditLogTab from './AuditLogTab'
import MonitoringTab from './MonitoringTab'
import styles from './Admin.module.css'

type Tab = 'users' | 'audit' | 'monitoring' | 'profile'



export default function AdminPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const isSuperadmin = user?.role === 'superadmin'
  const tab: Tab = (params.get('tab') as Tab) || 'users'

  const setTab = (t: Tab) => { setParams({ tab: t }) }

  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [resetId, setResetId] = useState<number | null>(null)
  const [deleteCtx, setDeleteCtx] = useState<{ id: number; username: string } | null>(null)
  const [usersRefresh, setUsersRefresh] = useState(0)
  const triggerRefresh = () => setUsersRefresh((v) => v + 1)

  const onToggle = async (id: number) => {
    try {
      await api.post(`/admin/users/${id}/toggle-active`)
      triggerRefresh()
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка переключения статуса'))
    }
  }

  const onDeleteAsk = async (id: number) => {
    try {
      const { data } = await api.get<{ username: string }>(`/admin/users/${id}`)
      setDeleteCtx({ id, username: data.username })
    } catch (e: unknown) {
      toast.error(errorMessage(e, 'Ошибка загрузки пользователя'))
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Admin Panel</h1>
      <div className={styles.tabs} role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'users'}
          className={`${styles.tab} ${tab === 'users' ? styles.tabActive : ''}`}
          onClick={() => setTab('users')}
        >
          Пользователи
        </button>
        <button
          role="tab"
          aria-selected={tab === 'audit'}
          className={`${styles.tab} ${tab === 'audit' ? styles.tabActive : ''}`}
          onClick={() => setTab('audit')}
        >
          Аудит-лог
        </button>
        {isSuperadmin && (
          <button
            role="tab"
            aria-selected={tab === 'monitoring'}
            className={`${styles.tab} ${tab === 'monitoring' ? styles.tabActive : ''}`}
            onClick={() => setTab('monitoring')}
          >
            Мониторинг
          </button>
        )}
        <button
          role="tab"
          aria-selected={tab === 'profile'}
          className={`${styles.tab} ${tab === 'profile' ? styles.tabActive : ''}`}
          onClick={() => setTab('profile')}
        >
          Мой профиль
        </button>
      </div>

      {tab === 'users' && (
        <UsersTab
          key={usersRefresh}
          onCreate={() => setShowCreate(true)}
          onEdit={(id) => setEditId(id)}
          onResetPassword={(id) => setResetId(id)}
          onToggle={onToggle}
          onDelete={onDeleteAsk}
        />
      )}
      {tab === 'audit' && <AuditLogTab />}
      {tab === 'monitoring' && isSuperadmin && <MonitoringTab />}
      {tab === 'profile' && <ProfileTab />}

      {showCreate && (
        <CreateUserModal onClose={() => setShowCreate(false)} onCreated={triggerRefresh} />
      )}
      {editId !== null && (
        <EditUserModal
          userId={editId}
          onClose={() => setEditId(null)}
          onSaved={triggerRefresh}
        />
      )}
      {resetId !== null && (
        <ResetPasswordModal userId={resetId} onClose={() => setResetId(null)} />
      )}
      {deleteCtx && (
        <ConfirmDeleteModal
          userId={deleteCtx.id}
          username={deleteCtx.username}
          onClose={() => setDeleteCtx(null)}
          onDeleted={triggerRefresh}
        />
      )}
    </div>
  )
}
