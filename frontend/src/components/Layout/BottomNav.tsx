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

interface NavItemDef {
  to: string
  icon: typeof Home
  label: string
  end?: boolean
}

export default function BottomNav() {
  const { user } = useAuth()
  if (!user) return null

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'

  const items: NavItemDef[] = [{ to: '/', icon: Home, label: 'Главная', end: true }]

  if (user.permissions.youtube) {
    items.push({ to: '/youtube', icon: Youtube, label: 'YouTube' })
  }
  if (user.permissions.converter) {
    items.push({ to: '/converter', icon: FileBox, label: 'Convert' })
  }
  if (user.permissions.image) {
    items.push({ to: '/image', icon: ImageIcon, label: 'Image' })
  }
  if (user.permissions.multidl) {
    items.push({ to: '/multidl', icon: Download, label: 'Multi' })
  }

  // Пятый пункт: профиль для обычных юзеров, админка для admin/superadmin
  if (isAdmin) {
    items.push({ to: '/admin', icon: Shield, label: 'Admin' })
  } else {
    items.push({ to: '/me', icon: UserIcon, label: 'ЛК' })
  }

  // Если получилось >5, оставляем первые 4 + админку/ЛК на 5й позиции
  const display = items.length > 5 ? [...items.slice(0, 4), items[items.length - 1]] : items

  return (
    <nav className={styles.bottomNav} aria-label="Основная навигация">
      {display.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `${styles.bottomNavItem} ${isActive ? styles.bottomNavItemActive : ''}`
          }
        >
          {({ isActive }) => (
            <>
              <item.icon className={styles.bottomNavIcon} aria-hidden="true" />
              <span
                className={styles.bottomNavLabel}
                aria-current={isActive ? 'page' : undefined}
              >
                {item.label}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
