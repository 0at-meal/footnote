import React from 'react'
import { StatusDot } from './StatusDot'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'ok' | 'warn' | 'danger' | 'neutral' | 'accent'
  size?: 'sm' | 'md'
  dot?: boolean
  pulse?: boolean
  icon?: React.ReactNode
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'md',
  dot = false,
  pulse = false,
  icon,
  children,
  className = '',
  style,
  ...props
}) => {
  return (
    <span
      className={`status-badge status-badge--${variant} ${className}`}
      style={{
        height: size === 'sm' ? '18px' : '22px',
        fontSize: size === 'sm' ? '11px' : '12px',
        padding: size === 'sm' ? '0 5px' : '0 8px',
        gap: '5px',
        ...style,
      }}
      {...props}
    >
      {dot && <StatusDot status={variant} pulse={pulse} size="sm" />}
      {icon}
      <span>{children}</span>
    </span>
  )
}
