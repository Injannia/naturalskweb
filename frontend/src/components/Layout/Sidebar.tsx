import { NavLink } from 'react-router-dom'
import {
  Home,
  Youtube,
  FileBox,
  Image as ImageIcon,
  Download,
  User as UserIcon,
  Shield,
} from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Layout.module.css'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  const moduleItems = [
    { to: '/youtube', icon: Youtube, label: 'YouTube Downloader', visible: user?.permissions.youtube },
    { to: '/converter', icon: FileBox, label: 'File Converter', visible: user?.permissions.converter },
    { to: '/image', icon: ImageIcon, label: 'Image Processor', visible: user?.permissions.image },
    { to: '/multidl', icon: Download, label: 'Multi downloader', visible: user?.permissions.multidl },
  ]

  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    `${styles.navItem} ${isActive ? styles.navItemActive : ''}`

  return (
    <>
      {isOpen && <div className={styles.overlay} onClick={onClose} />}
      <aside className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.sidebarLogo}>
          <span className={styles.sidebarLogoText}>
            Naturalsk<span className={styles.sidebarLogoAccent}>Web</span>
          </span>
        </div>

        <nav className={styles.sidebarNav}>
          <NavLink to="/" end onClick={onClose} className={navItemClass}>
            <Home className={styles.navIcon} />
            Главная
          </NavLink>

          <div className={styles.navDivider} />

          {moduleItems
            .filter((item) => item.visible)
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={navItemClass}
              >
                <item.icon className={styles.navIcon} />
                {item.label}
              </NavLink>
            ))}

          <div className={styles.navDivider} />

          {isAdmin ? (
            <NavLink to="/admin" onClick={onClose} className={navItemClass}>
              <Shield className={styles.navIcon} />
              Admin Panel
            </NavLink>
          ) : (
            <NavLink to="/me" onClick={onClose} className={navItemClass}>
              <UserIcon className={styles.navIcon} />
              Личный кабинет
            </NavLink>
          )}
        </nav>
      </aside>
    </>
  )
}
