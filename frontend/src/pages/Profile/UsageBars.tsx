import type { User } from '../../types'
import styles from './Profile.module.css'

interface Props {
  user: User
}

const MODULES: Array<{
  key: 'youtube' | 'converter' | 'image'
  label: string
  limitKey: 'youtube_daily' | 'convert_daily' | 'image_daily'
}> = [
  { key: 'youtube', label: 'YouTube', limitKey: 'youtube_daily' },
  { key: 'converter', label: 'Converter', limitKey: 'convert_daily' },
  { key: 'image', label: 'Image', limitKey: 'image_daily' },
]

function colorClass(used: number, limit: number): string {
  if (limit <= 0) return styles.barOk
  const pct = (used / limit) * 100
  if (pct >= 90) return styles.barDanger
  if (pct >= 70) return styles.barWarn
  return styles.barOk
}

function formatTimeUntilReset(resetDateIso: string | undefined): string {
  if (!resetDateIso) return ''
  const reset = new Date(resetDateIso + 'T00:00:00Z')
  const next = new Date(reset.getTime() + 24 * 60 * 60 * 1000)
  const diff = next.getTime() - Date.now()
  if (diff <= 0) return 'обновляются'
  const h = Math.floor(diff / (60 * 60 * 1000))
  const m = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000))
  return `${h} ч ${m} мин`
}

export default function UsageBars({ user }: Props) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Использование сегодня</h3>
      <div className={styles.bars}>
        {MODULES.map((m) => {
          const used = user.usage_today[m.key] ?? 0
          const limit = user.limits[m.limitKey] ?? 0
          const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
          return (
            <div key={m.key} className={styles.barRow}>
              <div className={styles.barLabel}>
                <span>{m.label}</span>
                <span className={styles.barCount}>
                  {used} / {limit}
                </span>
              </div>
              <div className={styles.barTrack}>
                <div
                  className={`${styles.barFill} ${colorClass(used, limit)}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
      <div className={styles.resetHint}>
        Лимиты обнулятся через {formatTimeUntilReset(user.usage_reset_date)}
      </div>
    </section>
  )
}
