import { useEffect, useState } from 'react'
import { toast } from 'react-toastify'
import { Monitor, Smartphone } from 'lucide-react'
import api from '../../api/client'
import { Button } from '../../components/ui'
import type { MySessionItem } from '../../types'
import styles from './Profile.module.css'

function shortUA(ua: string): string {
  if (!ua) return 'Неизвестно'
  let browser = ''
  if (/Firefox\/(\d+)/.test(ua)) browser = `Firefox ${ua.match(/Firefox\/(\d+)/)![1]}`
  else if (/Edg\/(\d+)/.test(ua)) browser = `Edge ${ua.match(/Edg\/(\d+)/)![1]}`
  else if (/Chrome\/(\d+)/.test(ua)) browser = `Chrome ${ua.match(/Chrome\/(\d+)/)![1]}`
  else if (/Safari\/(\d+)/.test(ua)) browser = `Safari ${ua.match(/Version\/(\d+)/)?.[1] ?? ''}`
  let os = ''
  if (/Windows/.test(ua)) os = 'Windows'
  else if (/Mac OS|Macintosh/.test(ua)) os = 'macOS'
  else if (/Android/.test(ua)) os = 'Android'
  else if (/iPhone|iPad/.test(ua)) os = 'iOS'
  else if (/Linux/.test(ua)) os = 'Linux'
  return [browser, os].filter(Boolean).join(' · ') || 'Иное'
}

function isMobileUA(ua: string): boolean {
  return /Android|iPhone|iPad|iPod|Mobile/.test(ua)
}

export default function SessionsList() {
  const [sessions, setSessions] = useState<MySessionItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api
      .get<MySessionItem[]>('/me/sessions')
      .then(({ data }) => setSessions(data))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const killOne = async (id: number) => {
    await api.delete(`/me/sessions/${id}`)
    toast.success('Сессия завершена')
    load()
  }

  const killOthers = async () => {
    await api.delete('/me/sessions')
    toast.success('Остальные сессии завершены')
    load()
  }

  if (loading) return <div>Загрузка сессий…</div>

  return (
    <>
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>Активные сессии</h2>
        <Button
          variant="secondary"
          size="sm"
          onClick={killOthers}
          disabled={sessions.length <= 1}
        >
          Завершить все, кроме текущей
        </Button>
      </div>
      <div className={styles.sessionList}>
        {sessions.map((s) => {
          const Icon = isMobileUA(s.user_agent) ? Smartphone : Monitor
          return (
            <div
              key={s.id}
              className={`${styles.sessionItem} ${s.is_current ? styles.sessionItemCurrent : ''}`}
            >
              <Icon size={20} aria-hidden="true" />
              <div className={styles.sessionInfo}>
                <div className={styles.sessionLine}>
                  <strong>{shortUA(s.user_agent)}</strong>
                  {s.is_current && <span className={styles.badge}>Эта сессия</span>}
                </div>
                <div className={styles.sessionMeta}>IP: {s.ip_address || '—'}</div>
                <div className={styles.sessionMeta}>
                  Создана: {new Date(s.created_at).toLocaleString('ru-RU')}
                </div>
              </div>
              {!s.is_current && (
                <Button variant="dangerOutline" size="sm" onClick={() => killOne(s.id)}>
                  Завершить
                </Button>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}
