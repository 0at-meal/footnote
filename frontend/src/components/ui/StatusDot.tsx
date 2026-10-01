import React from 'react'

export interface StatusDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  status?: 'ok' | 'warn' | 'danger' | 'neutral' | 'accent'
  pulse?: boolean
  size?: 'sm' | 'md' | 'lg'
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status = 'neutral',
  pulse = false,
  size = 'md',
  className = '',
  style,
  ...props
}) => {
  const sizePx = size === 'sm' ? 6 : size === 'lg' ? 10 : 8

  const colorMap = {
    ok: 'var(--ok)',
    warn: 'var(--warn)',
    danger: 'var(--danger)',
    neutral: 'var(--neutral)',
    accent: 'var(--accent)',
  }

  return (
    <span
      className={`fn-status-dot fn-status-dot--${status} ${className}`}
      style={{
        display: 'inline-block',
        width: `${sizePx}px`,
        height: `${sizePx}px`,
        borderRadius: '50%',
        backgroundColor: colorMap[status],
        flexShrink: 0,
        boxShadow: pulse ? `0 0 0 2px ${colorMap[status]}33` : undefined,
        animation: pulse ? 'status-pulse 1.5s ease-in-out infinite' : undefined,
        ...style,
      }}
      aria-hidden="true"
      {...props}
    />
  )
}
