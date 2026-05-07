import { useEffect, useState } from 'react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import type { AdminStats, SystemInfo } from '../../types'
import styles from './Admin.module.css'

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${d}д ${h}ч ${m}м`
}

export default function MonitoringTab() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [stats, setStats] = useState<AdminStats | null>(null)

  useEffect(() => {
    let stopped = false

    const load = async () => {
      if (stopped) return
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      try {
        const [s, st] = await Promise.all([
          api.get<SystemInfo>('/admin/system'),
          api.get<AdminStats>('/admin/stats'),
        ])
        if (stopped) return
        setSys(s.data)
        setStats(st.data)
      } catch {
        // Silently swallow — interceptor handles 401, transient errors will retry on next tick.
      }
    }

    load()
    const id = window.setInterval(load, 30_000)
    return () => {
      stopped = true
      window.clearInterval(id)
    }
  }, [])

  if (!sys || !stats) return <div>Загрузка...</div>

  const ramPct =
    sys.ram_total_mb > 0 ? Math.round((sys.ram_used_mb / sys.ram_total_mb) * 100) : 0
  const diskPct =
    sys.disk_total_gb > 0 ? Math.round((sys.disk_used_gb / sys.disk_total_gb) * 100) : 0

  return (
    <div>
      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>CPU</div>
          <div className={styles.cardValue}>{sys.cpu_percent.toFixed(1)}%</div>
          <div className={styles.cardBar}>
            <div className={styles.cardBarFill} style={{ width: `${sys.cpu_percent}%` }} />
          </div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>RAM</div>
          <div className={styles.cardValue}>
            {Math.round(sys.ram_used_mb)} / {Math.round(sys.ram_total_mb)} МБ
          </div>
          <div className={styles.cardBar}>
            <div className={styles.cardBarFill} style={{ width: `${ramPct}%` }} />
          </div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Disk</div>
          <div className={styles.cardValue}>
            {sys.disk_used_gb.toFixed(1)} / {sys.disk_total_gb.toFixed(1)} ГБ
          </div>
          <div className={styles.cardBar}>
            <div className={styles.cardBarFill} style={{ width: `${diskPct}%` }} />
          </div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Uptime</div>
          <div className={styles.cardValue}>{formatUptime(sys.uptime_seconds)}</div>
        </div>
      </div>

      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Downloads сегодня</div>
          <div className={styles.cardValue}>{stats.total_downloads_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Conversions сегодня</div>
          <div className={styles.cardValue}>{stats.total_conversions_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Image ops сегодня</div>
          <div className={styles.cardValue}>{stats.total_image_ops_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Storage</div>
          <div className={styles.cardValue}>{stats.storage_used_mb.toFixed(0)} МБ</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Активные сессии</div>
          <div className={styles.cardValue}>{stats.active_sessions}</div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardLabel}>Топ-5 пользователей сегодня</div>
        <table className={styles.table} style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th></th>
              <th>Имя</th>
              <th>Всего операций</th>
            </tr>
          </thead>
          <tbody>
            {stats.top_users.map((u) => (
              <tr key={u.user_id}>
                <td>
                  <AvatarImage userId={u.user_id} version={u.avatar_version} size={24} />
                </td>
                <td>{u.username}</td>
                <td>{u.total_today}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.versions}>
        Python {sys.python_version} · ffmpeg {sys.ffmpeg_version} · yt-dlp {sys.yt_dlp_version}
      </div>
    </div>
  )
}
