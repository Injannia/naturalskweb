import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../../stores/authStore'
import ProfileTab from '../Profile/ProfileTab'
import UsersTab from './UsersTab'
import styles from './Admin.module.css'

type Tab = 'users' | 'audit' | 'monitoring' | 'profile'

export default function AdminPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const isSuperadmin = user?.role === 'superadmin'
  const tab: Tab = (params.get('tab') as Tab) || 'users'

  const setTab = (t: Tab) => { setParams({ tab: t }) }

  // Заглушки — модалки появятся в Task 21
  const noop = () => alert('TODO Task 21')

  return (
    <div className={styles.page}>
      <h1>Admin Panel</h1>
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'users' ? styles.tabActive : ''}`}
          onClick={() => setTab('users')}
        >
          Пользователи
        </button>
        <button
          className={`${styles.tab} ${tab === 'audit' ? styles.tabActive : ''}`}
          onClick={() => setTab('audit')}
        >
          Аудит-лог
        </button>
        {isSuperadmin && (
          <button
            className={`${styles.tab} ${tab === 'monitoring' ? styles.tabActive : ''}`}
            onClick={() => setTab('monitoring')}
          >
            Мониторинг
          </button>
        )}
        <button
          className={`${styles.tab} ${tab === 'profile' ? styles.tabActive : ''}`}
          onClick={() => setTab('profile')}
        >
          Мой профиль
        </button>
      </div>

      {tab === 'users' && (
        <UsersTab
          onCreate={noop}
          onEdit={noop}
          onResetPassword={noop}
          onToggle={noop}
          onDelete={noop}
        />
      )}
      {tab === 'audit' && <div>Аудит-лог (Task 22)</div>}
      {tab === 'monitoring' && isSuperadmin && <div>Мониторинг (Task 23)</div>}
      {tab === 'profile' && <ProfileTab />}
    </div>
  )
}
