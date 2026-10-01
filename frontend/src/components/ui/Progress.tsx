import React from 'react'

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number // 0-100, undefined for indeterminate
  max?: number
  size?: 'sm' | 'md'
  variant?: 'accent' | 'ok' | 'warn' | 'danger'
}

export const Progress: React.FC<ProgressProps> = ({
  value,
  max = 100,
  size = 'md',
  variant = 'accent',
  className = '',
  style,
  ...props
}) => {
  const isIndeterminate = value === undefined
  const percentage = isIndeterminate ? 0 : Math.min(100, Math.max(0, (value / max) * 100))

  const height = size === 'sm' ? 4 : 8

  const variantColors = {
    accent: 'var(--accent)',
    ok: 'var(--ok)',
    warn: 'var(--warn)',
    danger: 'var(--danger)',
  }

  return (
    <div
      role="progressbar"
      aria-valuenow={isIndeterminate ? undefined : value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={`fn-progress ${className}`}
      style={{
        position: 'relative',
        width: '100%',
        height: `${height}px`,
        backgroundColor: 'var(--surface-2)',
        borderRadius: 'var(--fn-radius-pill)',
        overflow: 'hidden',
        border: '1px solid var(--border)',
        ...style,
      }}
      {...props}
    >
      <div
        style={{
          height: '100%',
          width: isIndeterminate ? '40%' : `${percentage}%`,
          backgroundColor: variantColors[variant],
          borderRadius: 'var(--fn-radius-pill)',
          transition: isIndeterminate ? 'none' : 'width var(--fn-motion-state)',
          animation: isIndeterminate ? 'fn-indeterminate 1.5s infinite linear' : 'none',
        }}
      />
    </div>
  )
}
