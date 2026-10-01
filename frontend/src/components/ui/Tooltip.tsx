import React, { useState } from 'react'

export interface TooltipProps {
  content: React.ReactNode
  children: React.ReactElement
  position?: 'top' | 'bottom' | 'left' | 'right'
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top',
}) => {
  const [isVisible, setIsVisible] = useState(false)

  const positionStyles: Record<string, React.CSSProperties> = {
    top: {
      bottom: 'calc(100% + 6px)',
      left: '50%',
      transform: 'translateX(-50%)',
    },
    bottom: {
      top: 'calc(100% + 6px)',
      left: '50%',
      transform: 'translateX(-50%)',
    },
    left: {
      right: 'calc(100% + 6px)',
      top: '50%',
      transform: 'translateY(-50%)',
    },
    right: {
      left: 'calc(100% + 6px)',
      top: '50%',
      transform: 'translateY(-50%)',
    },
  }

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      {isVisible && content && (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            ...positionStyles[position],
            backgroundColor: 'var(--surface-2)',
            color: 'var(--ink)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--fn-radius-sm)',
            padding: '4px 8px',
            fontSize: 'var(--fn-text-12)',
            whiteSpace: 'nowrap',
            boxShadow: 'var(--fn-shadow-md)',
            zIndex: 1100,
            pointerEvents: 'none',
          }}
        >
          {content}
        </div>
      )}
    </div>
  )
}
