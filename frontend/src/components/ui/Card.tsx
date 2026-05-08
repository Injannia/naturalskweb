import { HTMLAttributes, ReactNode } from 'react'
import styles from './Card.module.css'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'glass' | 'elevated'
  interactive?: boolean
  children?: ReactNode
}

export default function Card({
  variant = 'glass',
  interactive = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={`${styles.card} ${styles[variant]} ${interactive ? styles.interactive : ''} ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
