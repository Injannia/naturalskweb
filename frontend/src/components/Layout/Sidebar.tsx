import { NavLink } from 'react-router-dom'
import { Youtube, FileBox, Image, Shield } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Layout.module.css'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  const navItems = [
    {
      to: '/youtube',
      icon: Youtube,
      label: 'YouTube Downloader',
      visible: user?.permissions.youtube,
      enabled: true,
    },
    {
      to: '/converter',
      icon: FileBox,
      label: 'File Converter',
      visible: user?.permissions.converter,
      enabled: true,
    },
    {
      to: '/image',
      icon: Image,
      label: 'Image Processor',
      visible: user?.permissions.image,
      enabled: true,
    },
  ]

  return (
    <>
      {isOpen && <div className={styles.overlay} onClick={onClose} />}
      <aside
        className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : ''}`}
      >
        <div className={styles.sidebarLogo}>
          <span className={styles.sidebarLogoText}>
            Naturalsk<span className={styles.sidebarLogoAccent}>Web</span>
          </span>
        </div>

        <nav className={styles.sidebarNav}>
          {navItems
            .filter((item) => item.visible)
            .map((item) =>
              item.enabled ? (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                  }
                >
                  <item.icon className={styles.navIcon} />
                  {item.label}
                </NavLink>
              ) : (
                <div
                  key={item.to}
                  className={`${styles.navItem} ${styles.navItemDisabled}`}
                  aria-disabled="true"
                >
                  <item.icon className={styles.navIcon} />
                  {item.label}
                  <span className={styles.comingSoonBadge}>Скоро</span>
                </div>
              ),
            )}

          {isAdmin && (
            <>
              <div className={styles.navDivider} />
              <NavLink
                to="/admin"
                onClick={onClose}
                className={({ isActive }) =>
                  `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                }
              >
                <Shield className={styles.navIcon} />
                Admin Panel
              </NavLink>
            </>
          )}
        </nav>
      </aside>
    </>
  )
}
