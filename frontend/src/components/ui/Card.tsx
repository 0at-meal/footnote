import React from 'react'

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  elevated?: boolean
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ elevated = false, children, className = '', style, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`fn-card ${className}`}
        style={{
          backgroundColor: elevated ? 'var(--surface-2)' : 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--fn-radius-md)',
          boxShadow: elevated ? 'var(--fn-shadow-md)' : 'var(--fn-shadow-sm)',
          overflow: 'hidden',
          transition: 'border-color var(--fn-motion-hover), box-shadow var(--fn-motion-hover)',
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    )
  },
)
Card.displayName = 'Card'

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className = '', style, ...props }, ref) => (
    <div
      ref={ref}
      className={`fn-card-header ${className}`}
      style={{
        padding: '14px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  ),
)
CardHeader.displayName = 'CardHeader'

export const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ children, className = '', style, ...props }, ref) => (
    <h3
      ref={ref}
      className={`fn-card-title ${className}`}
      style={{
        margin: 0,
        fontSize: 'var(--fn-text-16)',
        fontWeight: 600,
        color: 'var(--ink)',
        ...style,
      }}
      {...props}
    >
      {children}
    </h3>
  ),
)
CardTitle.displayName = 'CardTitle'

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ children, className = '', style, ...props }, ref) => (
    <p
      ref={ref}
      className={`fn-card-desc ${className}`}
      style={{
        margin: '4px 0 0 0',
        fontSize: 'var(--fn-text-13)',
        color: 'var(--ink-muted)',
        ...style,
      }}
      {...props}
    >
      {children}
    </p>
  ),
)
CardDescription.displayName = 'CardDescription'

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className = '', style, ...props }, ref) => (
    <div
      ref={ref}
      className={`fn-card-content ${className}`}
      style={{
        padding: '16px',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  ),
)
CardContent.displayName = 'CardContent'

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className = '', style, ...props }, ref) => (
    <div
      ref={ref}
      className={`fn-card-footer ${className}`}
      style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        backgroundColor: 'var(--surface-2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '8px',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  ),
)
CardFooter.displayName = 'CardFooter'
