import type { CSSProperties } from 'react'
import { User as UserIcon } from 'lucide-react'
import { useAuthedImage } from '../hooks/useAuthedImage'
import styles from './AvatarImage.module.css'

interface Props {
  userId: number | undefined
  version?: number
  size?: number
  className?: string
}

export default function AvatarImage({ userId, version = 0, size = 32, className }: Props) {
  const url = userId ? `/users/${userId}/avatar?v=${version}` : null
  const src = useAuthedImage(url)

  const style: CSSProperties = {
    width: size,
    height: size,
    minWidth: size,
  }

  if (src) {
    return <img src={src} alt="" className={`${styles.avatar} ${className ?? ''}`} style={style} />
  }
  return (
    <div className={`${styles.fallback} ${className ?? ''}`} style={style}>
      <UserIcon size={Math.round(size * 0.55)} />
    </div>
  )
}
