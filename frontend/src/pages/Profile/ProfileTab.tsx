import { useEffect, useState } from 'react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import type { User } from '../../types'
import { useAuth } from '../../stores/authStore'
import UsageBars from './UsageBars'
import styles from './Profile.module.css'

function formatDate(iso: string | undefined | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU')
}

export default function ProfileTab() {
  const { user: authUser, setUser } = useAuth()
  const [me, setMe] = useState<User | null>(authUser)

  useEffect(() => {
    api
      .get<User>('/me')
      .then(({ data }) => {
        setMe(data)
        setUser(data)
      })
      .catch(() => {})
  }, [])

  if (!me) return null

  return (
    <div className={styles.tab}>
      <section className={styles.section}>
        <div className={styles.header}>
          <AvatarImage userId={me.id} version={me.avatar_version ?? 0} size={128} />
          <div className={styles.headerInfo}>
            <h2 className={styles.username}>{me.username}</h2>
            <div className={styles.role}>{me.role}</div>
            <div className={styles.headerMeta}>
              <div>Создан: {formatDate(me.created_at)}</div>
              <div>Последний вход: {formatDate(me.last_login)}</div>
            </div>
          </div>
        </div>
      </section>

      <UsageBars user={me} />
    </div>
  )
}
