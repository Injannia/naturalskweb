import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import AuroraBackground from '../AuroraBackground/AuroraBackground'
import StarryBackground from '../StarryBackground/StarryBackground'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import styles from './Layout.module.css'

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Prevent background scrolling when the mobile sidebar is open
  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [sidebarOpen])

  return (
    <>
      <AuroraBackground />
      <StarryBackground />
      <div className={styles.layout}>
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <Topbar
          onMenuClick={() => setSidebarOpen((prev) => !prev)}
          sidebarOpen={sidebarOpen}
        />
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </>
  )
}
