import { forwardRef, InputHTMLAttributes, ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import styles from './Input.module.css'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
  error?: ReactNode
  helper?: ReactNode
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helper, className = '', id, ...rest }, ref) => {
    const inputId = id ?? `input-${Math.random().toString(36).slice(2, 9)}`
    return (
      <div className={styles.field}>
        {label && <label htmlFor={inputId} className={styles.label}>{label}</label>}
        <input
          ref={ref}
          id={inputId}
          className={`${styles.input} ${error ? styles.inputError : ''} ${className}`}
          aria-invalid={!!error}
          {...rest}
        />
        {error ? (
          <span className={styles.error}>
            <AlertCircle size={14} aria-hidden="true" />
            {error}
          </span>
        ) : helper ? (
          <span className={styles.helper}>{helper}</span>
        ) : null}
      </div>
    )
  },
)
Input.displayName = 'Input'
export default Input
