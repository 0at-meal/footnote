import React from 'react'

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: string | number
  height?: string | number
  variant?: 'text' | 'circular' | 'rectangular'
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height,
  variant = 'text',
  className = '',
  style,
  ...props
}) => {
  const getRadius = () => {
    if (variant === 'circular') return '50%'
    if (variant === 'text') return 'var(--fn-radius-sm)'
    return 'var(--fn-radius-md)'
  }

  return (
    <div
      className={`fn-skeleton ${className}`}
      style={{
        width: width ?? (variant === 'text' ? '100%' : '40px'),
        height: height ?? (variant === 'text' ? '14px' : '40px'),
        borderRadius: getRadius(),
        backgroundColor: 'var(--surface-2)',
        animation: 'fn-skeleton-pulse 1.6s ease-in-out infinite',
        ...style,
      }}
      aria-hidden="true"
      {...props}
    />
  )
}
