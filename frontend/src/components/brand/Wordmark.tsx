import React from 'react'

export interface WordmarkProps extends React.HTMLAttributes<HTMLSpanElement> {
  size?: 'sm' | 'md' | 'lg'
  marker?: string
}

export const Wordmark: React.FC<WordmarkProps> = ({
  size = 'md',
  marker = '*',
  className = '',
  style,
  ...props
}) => {
  const fontSizes = {
    sm: { base: '16px', marker: '10px', offset: '-3px' },
    md: { base: '22px', marker: '13px', offset: '-4px' },
    lg: { base: '32px', marker: '18px', offset: '-6px' },
  }

  const { base, marker: markerSize, offset } = fontSizes[size]

  return (
    <span
      className={`fn-wordmark ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        fontFamily: 'var(--fn-font-serif)',
        fontSize: base,
        fontWeight: 600,
        letterSpacing: '-0.02em',
        color: 'var(--ink)',
        lineHeight: 1,
        userSelect: 'none',
        ...style,
      }}
      aria-label="Footnote"
      {...props}
    >
      <span>footnote</span>
      <sup
        className="fn-wordmark__marker"
        style={{
          fontFamily: 'var(--fn-font-sans)',
          fontSize: markerSize,
          fontWeight: 700,
          color: 'var(--accent)',
          marginLeft: '2px',
          transform: `translateY(${offset})`,
          display: 'inline-block',
          lineHeight: 1,
        }}
        aria-hidden="true"
      >
        {marker}
      </sup>
    </span>
  )
}
