import { NavLink } from 'react-router-dom'
import { Youtube, FileBox, Image as ImageIcon, User as UserIcon, Shield } from 'lucide-react'
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
    tiles.push({ to: '/youtube', icon: Youtube, title: 'YouTube Downloader', description: 'Скачивание видео' })
  }
  if (user.permissions.converter) {
    tiles.push({ to: '/converter', icon: FileBox, title: 'File Converter', description: 'Конвертация файлов' })
  }
  if (user.permissions.image) {
    tiles.push({ to: '/image', icon: ImageIcon, title: 'Image Processor', description: 'Обработка изображений' })
  }
  if (isAdmin) {
    tiles.push({ to: '/admin', icon: Shield, title: 'Admin Panel', description: 'Управление и мониторинг' })
  } else {
    tiles.push({ to: '/me', icon: UserIcon, title: 'Личный кабинет', description: 'Профиль и статистика' })
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.logo}>
        <span className={styles.logoText}>
          Naturalsk<span className={styles.logoAccent}>Web</span>
        </span>
        <p className={styles.subtitle}>Закрытая рабочая среда</p>
      </div>

      <div className={styles.grid}>
        {tiles.map((t) => (
          <NavLink key={t.to} to={t.to} className={styles.tile}>
            <t.icon className={styles.tileIcon} />
            <div className={styles.tileTitle}>{t.title}</div>
            <div className={styles.tileDesc}>{t.description}</div>
          </NavLink>
        ))}
      </div>
    </div>
  )
}
