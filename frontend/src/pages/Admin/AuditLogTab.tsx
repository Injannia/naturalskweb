import { useEffect, useState, useCallback } from 'react'
import { Download } from 'lucide-react'
import api from '../../api/client'
import type { AuditLogItem, AuditLogListResponse } from '../../types'
import styles from './Admin.module.css'

const PAGE = 50
const ACTIONS = [
  '',
  'login',
  'logout',
  'login_failed',
  'change_password',
  'user_created',
  'user_updated',
  'user_deleted',
  'user_password_reset',
  'user_toggled_active',
  'session_killed_by_admin',
  'username_changed',
  'avatar_updated',
  'avatar_removed',
]

export default function AuditLogTab() {
  const [items, setItems] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const buildQuery = useCallback(() => {
    const p = new URLSearchParams()
    p.set('offset', String(offset))
    p.set('limit', String(PAGE))
    if (action) p.set('action', action)
    if (from) p.set('from', from)
    if (to) p.set('to', to)
    return p.toString()
  }, [offset, action, from, to])

  useEffect(() => {
    api
      .get<AuditLogListResponse>(`/admin/audit-log?${buildQuery()}`)
      .then(({ data }) => {
        setItems(data.items)
        setTotal(data.total)
      })
  }, [buildQuery])

  const downloadCsv = async () => {
    const r = await api.get(`/admin/audit-log/export.csv?${buildQuery()}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'audit-log.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <select
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setOffset(0)
          }}
        >
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a || 'Все действия'}
            </option>
          ))}
        </select>
        <input
          type="datetime-local"
          value={from}
          onChange={(e) => {
            setFrom(e.target.value)
            setOffset(0)
          }}
          aria-label="С даты"
        />
        <input
          type="datetime-local"
          value={to}
          onChange={(e) => {
            setTo(e.target.value)
            setOffset(0)
          }}
          aria-label="По дату"
        />
        <div className={styles.toolbarSpacer} />
        <button className={styles.iconBtn} onClick={downloadCsv}>
          <Download size={14} /> CSV
        </button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Дата</th>
            <th>Пользователь</th>
            <th>Действие</th>
            <th>IP</th>
            <th>Детали</th>
          </tr>
        </thead>
        <tbody>
          {items.map((l) => (
            <tr key={l.id}>
              <td>{new Date(l.created_at).toLocaleString('ru-RU')}</td>
              <td>{l.username ?? '—'}</td>
              <td>
                <code>{l.action}</code>
              </td>
              <td className={styles.usageCompact}>{l.ip_address || '—'}</td>
              <td>
                {l.details ? (
                  <button
                    className={styles.iconBtn}
                    onClick={() => setExpanded(expanded === l.id ? null : l.id)}
                  >
                    {expanded === l.id ? '▼' : '▶'}
                  </button>
                ) : (
                  '—'
                )}
                {expanded === l.id && l.details && (
                  <pre
                    style={{
                      background: 'var(--bg-secondary, #2a2a2a)',
                      padding: 8,
                      borderRadius: 4,
                      fontSize: 12,
                      marginTop: 4,
                      overflow: 'auto',
                    }}
                  >
                    {JSON.stringify(l.details, null, 2)}
                  </pre>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.pagination}>
        <span className={styles.pageInfo}>
          {total === 0 ? '0 из 0' : `${offset + 1}–${Math.min(offset + PAGE, total)} из ${total}`}
        </span>
        <button
          className={styles.iconBtn}
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
        >
          Назад
        </button>
        <button
          className={styles.iconBtn}
          disabled={offset + PAGE >= total}
          onClick={() => setOffset(offset + PAGE)}
        >
          Вперёд
        </button>
      </div>
    </div>
  )
}
