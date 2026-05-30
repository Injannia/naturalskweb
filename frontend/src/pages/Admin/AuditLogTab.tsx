import { useEffect, useState, useCallback } from 'react'
import { Download } from 'lucide-react'
import api from '../../api/client'
import { Card, Button } from '../../components/ui'
import type { AuditLogItem, AuditLogListResponse } from '../../types'
import styles from './Admin.module.css'

const PAGE = 50
const ACTIONS = [
  '',
  'login',
  'logout',
  'login_failed',
  'account_locked',
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

function actionChipClass(action: string): string {
  if (action === 'login_failed' || action === 'user_deleted' || action === 'account_locked') return styles.actionChipDanger
  if (action === 'login' || action === 'logout' || action === 'change_password') return styles.actionChipAuth
  if (action.startsWith('user_') || action === 'session_killed_by_admin') return styles.actionChipUser
  if (action === 'user_password_reset' || action === 'user_toggled_active') return styles.actionChipWarning
  if (action === 'avatar_updated' || action === 'avatar_removed' || action === 'username_changed') return styles.actionChipSuccess
  return ''
}

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
    // <input type="datetime-local"> yields a local wall-clock string with no
    // timezone; the backend compares against UTC timestamps. Convert to UTC
    // ISO (Z) so the filter bounds mean what the user picked, not a value
    // shifted by their UTC offset.
    if (from) p.set('from', new Date(from).toISOString())
    if (to) p.set('to', new Date(to).toISOString())
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
    <Card variant="glass">
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
          lang="ru-RU"
          value={from}
          onChange={(e) => {
            setFrom(e.target.value)
            setOffset(0)
          }}
          aria-label="С даты"
        />
        <input
          type="datetime-local"
          lang="ru-RU"
          value={to}
          onChange={(e) => {
            setTo(e.target.value)
            setOffset(0)
          }}
          aria-label="По дату"
        />
        <div className={styles.toolbarSpacer} />
        <Button variant="secondary" size="sm" leftIcon={<Download size={14} />} onClick={downloadCsv}>
          CSV
        </Button>
      </div>

      <div style={{ overflowX: 'auto' }}>
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
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className={styles.emptyState}>Нет записей</td>
              </tr>
            )}
            {items.map((l) => (
              <tr key={l.id}>
                <td>{new Date(l.created_at).toLocaleString('ru-RU')}</td>
                <td>{l.username ?? '—'}</td>
                <td>
                  <span className={`${styles.actionChip} ${actionChipClass(l.action)}`}>
                    {l.action}
                  </span>
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
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border)',
                        padding: 'var(--space-3)',
                        borderRadius: 'var(--radius-md)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 12,
                        marginTop: 'var(--space-2)',
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
      </div>

      <div className={styles.pagination}>
        <span className={styles.pageInfo}>
          {total === 0 ? '0 из 0' : `${offset + 1}–${Math.min(offset + PAGE, total)} из ${total}`}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
        >
          Назад
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={offset + PAGE >= total}
          onClick={() => setOffset(offset + PAGE)}
        >
          Вперёд
        </Button>
      </div>
    </Card>
  )
}
