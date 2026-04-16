import type { LucideIcon } from 'lucide-react'

interface Props {
  icon: LucideIcon
  title: string
  description: string
}

export default function PlaceholderPage({ icon: Icon, title, description }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - var(--topbar-height) - 4rem)',
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease',
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 'var(--space-6)',
        }}
      >
        <Icon size={32} style={{ color: 'var(--accent)' }} />
      </div>
      <h1
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--fs-xl)',
          fontWeight: 600,
          color: 'var(--text-primary)',
          marginBottom: 'var(--space-3)',
        }}
      >
        {title}
      </h1>
      <p
        style={{
          fontSize: 'var(--fs-sm)',
          color: 'var(--text-secondary)',
          maxWidth: 400,
          lineHeight: 1.6,
        }}
      >
        {description}
      </p>
    </div>
  )
}
