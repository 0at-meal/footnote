import React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  helperText?: string
  error?: string
  tabularNums?: boolean
  leftAddon?: React.ReactNode
  rightAddon?: React.ReactNode
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      helperText,
      error,
      tabularNums = false,
      leftAddon,
      rightAddon,
      className = '',
      id,
      ...props
    },
    ref,
  ) => {
    const inputId = id || (label ? `input-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)

    return (
      <div className="fn-input-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {label && (
          <label
            htmlFor={inputId}
            style={{
              fontSize: 'var(--fn-text-12)',
              fontWeight: 500,
              color: error ? 'var(--danger)' : 'var(--ink-secondary)',
            }}
          >
            {label}
          </label>
        )}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            border: `1px solid ${error ? 'var(--danger)' : 'var(--border)'}`,
            borderRadius: 'var(--fn-radius-sm)',
            backgroundColor: 'var(--surface)',
            padding: '0 8px',
            transition: 'border-color var(--fn-motion-hover), box-shadow var(--fn-motion-hover)',
          }}
          className="fn-input-container"
        >
          {leftAddon && <div style={{ marginRight: '6px', color: 'var(--ink-muted)' }}>{leftAddon}</div>}
          <input
            ref={ref}
            id={inputId}
            className={`${tabularNums ? 'tabular-nums ' : ''}${className}`}
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              background: 'transparent',
              color: 'var(--ink)',
              fontFamily: tabularNums ? 'var(--fn-font-mono)' : 'var(--fn-font-sans)',
              fontSize: 'var(--fn-text-13)',
              height: 'var(--fn-control-h-md)',
              padding: 0,
            }}
            aria-invalid={!!error}
            aria-describedby={error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
            {...props}
          />
          {rightAddon && <div style={{ marginLeft: '6px', color: 'var(--ink-muted)' }}>{rightAddon}</div>}
        </div>
        {error ? (
          <span
            id={`${inputId}-error`}
            style={{ fontSize: 'var(--fn-text-12)', color: 'var(--danger)', marginTop: '2px' }}
            role="alert"
          >
            {error}
          </span>
        ) : helperText ? (
          <span
            id={`${inputId}-helper`}
            style={{ fontSize: 'var(--fn-text-12)', color: 'var(--ink-muted)', marginTop: '2px' }}
          >
            {helperText}
          </span>
        ) : null}
      </div>
    )
  },
)

Input.displayName = 'Input'
