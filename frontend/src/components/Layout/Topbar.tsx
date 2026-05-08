import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Menu, X } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import AvatarImage from '../AvatarImage'
import styles from './Layout.module.css'

interface TopbarProps {
  onMenuClick: () => void
  sidebarOpen: boolean
}

export default function Topbar({ onMenuClick, sidebarOpen }: TopbarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className={`${styles.topbar} ${scrolled ? styles.topbarScrolled : ''}`}>
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
          <AvatarImage userId={user?.id} version={user?.avatar_version ?? 0} size={36} accentBorder />
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
