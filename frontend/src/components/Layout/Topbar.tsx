import { useNavigate } from 'react-router-dom'
import { LogOut, Menu, X } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Layout.module.css'

interface TopbarProps {
  onMenuClick: () => void
  sidebarOpen: boolean
}

export default function Topbar({ onMenuClick, sidebarOpen }: TopbarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeft}>
        <button
          className={styles.menuBtn}
          onClick={onMenuClick}
          aria-label={sidebarOpen ? 'Закрыть меню' : 'Открыть меню'}
          aria-expanded={sidebarOpen}
        >
          {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
        <span className={styles.topbarTitle}>NaturalskWeb</span>
      </div>

      <div className={styles.topbarRight}>
        <div className={styles.userInfo}>
          <div className={styles.userAvatar}>
            {user?.username.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className={styles.userName}>{user?.username}</div>
            <div className={styles.userRole}>{user?.role}</div>
          </div>
        </div>

        <button className={styles.logoutBtn} onClick={handleLogout}>
          <LogOut size={16} />
          Выход
        </button>
      </div>
    </header>
  )
}
