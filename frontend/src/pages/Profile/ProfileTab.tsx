import { useEffect, useState } from 'react'
import api from '../../api/client'
import type { User } from '../../types'
import { useAuth } from '../../stores/authStore'
import { Card } from '../../components/ui'
import UsageBars from './UsageBars'
import SessionsList from './SessionsList'
import ChangeUsernameForm from './ChangeUsernameForm'
import ChangePasswordForm from './ChangePasswordForm'
import AvatarUploader from './AvatarUploader'
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
    <div className={styles.wrapper}>
      <Card variant="glass" className={styles.avatarCard}>
        <AvatarUploader />
        <div>
          <div className={styles.username}>{me.username}</div>
          <div className={styles.role}>{me.role}</div>
          <div className={styles.headerMeta}>
            <div>Создан: {formatDate(me.created_at)}</div>
            <div>Последний вход: {formatDate(me.last_login)}</div>
          </div>
        </div>
      </Card>

      <div className={styles.sections}>
        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Имя пользователя</h2>
          <ChangeUsernameForm />
        </Card>

        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Использование сегодня</h2>
          <UsageBars user={me} />
        </Card>

        <Card variant="glass">
          <SessionsList />
        </Card>

        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Безопасность</h2>
          <ChangePasswordForm />
        </Card>
      </div>
    </div>
  )
}
