import styles from './AuroraBackground.module.css'

export default function AuroraBackground() {
  return (
    <div className={styles.layer} aria-hidden="true">
      <div className={styles.mesh} />
      <div className={`${styles.blob} ${styles.blob1}`} />
      <div className={`${styles.blob} ${styles.blob2}`} />
    </div>
  )
}
