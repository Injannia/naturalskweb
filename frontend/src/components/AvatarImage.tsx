import type { CSSProperties } from 'react'
import { User as UserIcon } from 'lucide-react'
import { useAuthedImage } from '../hooks/useAuthedImage'
import styles from './AvatarImage.module.css'

interface Props {
  userId: number | undefined
  version?: number
  size?: number
  className?: string
  accentBorder?: boolean
}

export default function AvatarImage({
  userId,
  version = 0,
  size = 32,
  className,
  accentBorder = false,
}: Props) {
  // Skip the fetch when there's no avatar yet (version === 0): the backend
  // would 404 and we'd render the same fallback anyway.
  const url = userId && version > 0 ? `/users/${userId}/avatar?v=${version}` : null
  const src = useAuthedImage(url)

  const innerSize = accentBorder ? size - 4 : size
  const style: CSSProperties = {
    width: innerSize,
    height: innerSize,
    minWidth: innerSize,
  }

  const inner = src ? (
    <img src={src} alt="" className={styles.avatar} style={style} />
  ) : (
    <div className={styles.fallback} style={style}>
      <UserIcon size={Math.round(innerSize * 0.55)} />
    </div>
  )

  if (accentBorder) {
    return (
      <span
        className={`${styles.accentBorder} ${className ?? ''}`}
        style={{ width: size, height: size, minWidth: size }}
      >
        {inner}
      </span>
    )
  }

  return src ? (
    <img src={src} alt="" className={`${styles.avatar} ${className ?? ''}`} style={style} />
  ) : (
    <div className={`${styles.fallback} ${className ?? ''}`} style={style}>
      <UserIcon size={Math.round(innerSize * 0.55)} />
    </div>
  )
}
