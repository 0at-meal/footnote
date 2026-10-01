import React from 'react'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  helperText?: string
  error?: string
  options?: SelectOption[]
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      helperText,
      error,
      options,
      children,
      className = '',
      id,
      ...props
    },
    ref,
  ) => {
    const selectId = id || (label ? `select-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)

    return (
      <div className="fn-select-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {label && (
          <label
            htmlFor={selectId}
            style={{
              fontSize: 'var(--fn-text-12)',
              fontWeight: 500,
              color: error ? 'var(--danger)' : 'var(--ink-secondary)',
            }}
          >
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={className}
          style={{
            height: 'var(--fn-control-h-md)',
            padding: '0 10px',
            border: `1px solid ${error ? 'var(--danger)' : 'var(--border)'}`,
            borderRadius: 'var(--fn-radius-sm)',
            backgroundColor: 'var(--surface)',
            color: 'var(--ink)',
            fontFamily: 'var(--fn-font-sans)',
            fontSize: 'var(--fn-text-13)',
            outline: 'none',
            cursor: 'pointer',
          }}
          aria-invalid={!!error}
          aria-describedby={error ? `${selectId}-error` : helperText ? `${selectId}-helper` : undefined}
          {...props}
        >
          {options
            ? options.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </option>
              ))
            : children}
        </select>
        {error ? (
          <span
            id={`${selectId}-error`}
            style={{ fontSize: 'var(--fn-text-12)', color: 'var(--danger)', marginTop: '2px' }}
            role="alert"
          >
            {error}
          </span>
        ) : helperText ? (
          <span
            id={`${selectId}-helper`}
            style={{ fontSize: 'var(--fn-text-12)', color: 'var(--ink-muted)', marginTop: '2px' }}
          >
            {helperText}
          </span>
        ) : null}
      </div>
    )
  },
)

Select.displayName = 'Select'
