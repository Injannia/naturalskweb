import ProfileTab from './ProfileTab'
import styles from './Profile.module.css'

export default function ProfilePage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Личный кабинет</h1>
      <ProfileTab />
    </div>
  )
}
