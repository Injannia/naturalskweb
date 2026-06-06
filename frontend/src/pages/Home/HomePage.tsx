import { NavLink } from 'react-router-dom'
import { Youtube, FileBox, Image as ImageIcon, Download, User as UserIcon, Shield } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Home.module.css'

interface Tile {
  to: string
  icon: typeof Youtube
  title: string
  description: string
}

export default function HomePage() {
  const { user } = useAuth()
  if (!user) return null

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  const tiles: Tile[] = []

  if (user.permissions.youtube) {
    tiles.push({ to: '/youtube', icon: Youtube, title: 'YouTube Downloader', description: 'Скачивание видео и плейлистов' })
  }
  if (user.permissions.converter) {
    tiles.push({ to: '/converter', icon: FileBox, title: 'File Converter', description: 'Конвертация документов и медиа' })
  }
  if (user.permissions.image) {
    tiles.push({ to: '/image', icon: ImageIcon, title: 'Image Processor', description: 'Удаление фона и водяных знаков' })
  }
  if (user.permissions.multidl) {
    tiles.push({ to: '/multidl', icon: Download, title: 'Multi downloader', description: 'Видео с Pinterest, Twitter/X, TikTok, VK' })
  }
  if (isAdmin) {
    tiles.push({ to: '/admin', icon: Shield, title: 'Admin Panel', description: 'Управление пользователями и мониторинг' })
  } else {
    tiles.push({ to: '/me', icon: UserIcon, title: 'Личный кабинет', description: 'Профиль, сессии и безопасность' })
  }

  const totalAvailable = [user.permissions.youtube, user.permissions.converter, user.permissions.image, user.permissions.multidl].filter(Boolean).length
  const status = totalAvailable === 4 ? 'Все модули доступны' : `${totalAvailable} из 4 модулей`

  return (
    <div className={styles.wrapper}>
      <div className={styles.hero}>
        <h1 className={styles.logo}>Naturalsk</h1>
        <p className={styles.greeting}>Привет, {user.username}</p>
        <p className={styles.statusLine}>{status}</p>
      </div>

      <div className={styles.grid}>
        {tiles.map((t) => (
          <NavLink key={t.to} to={t.to} className={styles.tile}>
            <t.icon className={styles.tileIcon} aria-hidden="true" />
            <div>
              <div className={styles.tileTitle}>{t.title}</div>
              <div className={styles.tileDesc}>{t.description}</div>
            </div>
          </NavLink>
        ))}
      </div>
    </div>
  )
}
