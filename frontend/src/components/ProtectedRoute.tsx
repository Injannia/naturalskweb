import { Navigate } from 'react-router-dom'
import { useAuth } from '../stores/authStore'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredPermission?: 'youtube' | 'converter' | 'image'
  adminOnly?: boolean
}

export default function ProtectedRoute({
  children,
  requiredPermission,
  adminOnly,
}: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-primary)',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        Загрузка...
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />
  }

  if (user.must_change_password) {
    return <Navigate to="/change-password" replace />
  }

  if (adminOnly && user.role !== 'admin' && user.role !== 'superadmin') {
    return <Navigate to="/youtube" replace />
  }

  if (requiredPermission && !user.permissions[requiredPermission]) {
    return <Navigate to="/youtube" replace />
  }

  return <>{children}</>
}
