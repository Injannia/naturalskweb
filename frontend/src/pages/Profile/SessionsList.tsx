import { useEffect, useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
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

  if (loading) return <div className={styles.section}>Загрузка сессий...</div>

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>Активные сессии</h3>
        <button
          className={styles.btnSecondary}
          onClick={killOthers}
          disabled={sessions.length <= 1}
        >
          Завершить все, кроме текущей
        </button>
      </div>
      <div className={styles.sessionList}>
        {sessions.map((s) => (
          <div key={s.id} className={styles.sessionItem}>
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
              <button className={styles.btnDanger} onClick={() => killOne(s.id)}>
                Завершить
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
