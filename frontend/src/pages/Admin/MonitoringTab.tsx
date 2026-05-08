import { useEffect, useState } from 'react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { Card } from '../../components/ui'
import type { AdminStats, SystemInfo } from '../../types'
import styles from './Admin.module.css'

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${d}д ${h}ч ${m}м`
}

interface GaugeProps {
  value: number // 0..100
  label: string
  unit?: string
}

function AuroraGauge({ value, label, unit = '%' }: GaugeProps) {
  const radius = 50
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - Math.min(100, Math.max(0, value)) / 100)
  return (
    <div className={styles.gauge}>
      <svg className={styles.gaugeSvg} viewBox="0 0 120 120">
        <defs>
          <linearGradient id="aurora-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366F1" />
            <stop offset="50%" stopColor="#A855F7" />
            <stop offset="100%" stopColor="#EC4899" />
          </linearGradient>
        </defs>
        <circle className={styles.gaugeTrack} cx="60" cy="60" r={radius} />
        <circle
          className={styles.gaugeFill}
          cx="60"
          cy="60"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
        />
      </svg>
      <div className={styles.gaugeLabel}>
        <span className={styles.gaugeValue}>
          {value.toFixed(0)}
          <span style={{ fontSize: 'var(--fs-base)', color: 'var(--text-muted)' }}>{unit}</span>
        </span>
        <span className={styles.gaugeUnit}>{label}</span>
      </div>
    </div>
  )
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
    sys.ram_total_mb > 0 ? (sys.ram_used_mb / sys.ram_total_mb) * 100 : 0
  const diskPct =
    sys.disk_total_gb > 0 ? (sys.disk_used_gb / sys.disk_total_gb) * 100 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <Card variant="glass">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)', justifyContent: 'space-around' }}>
          <AuroraGauge value={sys.cpu_percent} label="CPU" />
          <AuroraGauge value={ramPct} label="RAM" />
          <AuroraGauge value={diskPct} label="Disk" />
          <div className={styles.gauge} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <span className={styles.gaugeValue}>{formatUptime(sys.uptime_seconds)}</span>
            <span className={styles.gaugeUnit}>Uptime</span>
          </div>
        </div>
      </Card>

      <div className={styles.cards}>
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
          <div className={styles.cardLabel}>Активные сессии</div>
          <div className={styles.cardValue}>{stats.active_sessions}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Storage</div>
          <div className={styles.cardValue}>{stats.storage_used_mb.toFixed(0)} МБ</div>
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
      </div>

      <Card variant="glass">
        <div className={styles.cardLabel}>Топ-5 пользователей сегодня</div>
        <table className={styles.table} style={{ marginTop: 'var(--space-3)' }}>
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
        <div className={styles.versions}>
          Python {sys.python_version} · ffmpeg {sys.ffmpeg_version} · yt-dlp {sys.yt_dlp_version}
        </div>
      </Card>
    </div>
  )
}
