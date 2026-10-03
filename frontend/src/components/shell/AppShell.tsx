import React, { useState, useEffect } from 'react'
import { Wordmark } from '../brand/Wordmark'
import { Sun, Moon, LayoutGrid, ChevronRight } from 'lucide-react'

export interface BreadcrumbItem {
  label: string
  onClick?: () => void
  active?: boolean
}

export interface AppShellProps {
  breadcrumbs?: BreadcrumbItem[]
  currentRoute?: 'app' | 'design'
  onNavigate?: (route: 'app' | 'design') => void
  /** Show the dev-only design-system link (D7). App passes import.meta.env.DEV. */
  showDesignLink?: boolean
  /** Persistent service warning (e.g. degraded PDF parser, D1). Shown on every screen. */
  serviceWarning?: string | null
  children: React.ReactNode
}

export const AppShell: React.FC<AppShellProps> = ({
  breadcrumbs = [],
  currentRoute = 'app',
  onNavigate,
  showDesignLink = false,
  serviceWarning = null,
  children,
}) => {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window !== 'undefined') {
      const savedTheme = localStorage.getItem('fn-theme') as 'light' | 'dark' | null
      if (savedTheme) return savedTheme
    }
    // Appendix A: light-first "paper and ink"; dark is the second theme (D7).
    return 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const toggleTheme = () => {
    const nextTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(nextTheme)
    document.documentElement.setAttribute('data-theme', nextTheme)
    localStorage.setItem('fn-theme', nextTheme)
  }

  return (
    <div
      className="fn-app-shell"
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        backgroundColor: 'var(--bg)',
        color: 'var(--ink)',
      }}
    >
      {/* Top Bar Header */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: '48px',
          padding: '0 20px',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--surface)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          boxShadow: 'var(--fn-shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            type="button"
            onClick={() => onNavigate?.('app')}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Footnote Home"
          >
            <Wordmark size="sm" />
          </button>

          {/* Breadcrumbs */}
          {breadcrumbs.length > 0 && (
            <nav
              aria-label="Breadcrumb"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--fn-text-12)' }}
            >
              <span style={{ color: 'var(--border-strong)' }}>|</span>
              {breadcrumbs.map((crumb, idx) => {
                const isLast = idx === breadcrumbs.length - 1
                return (
                  <React.Fragment key={idx}>
                    {idx > 0 && (
                      <ChevronRight size={12} style={{ color: 'var(--ink-muted)' }} aria-hidden="true" />
                    )}
                    {crumb.onClick && !isLast ? (
                      <button
                        type="button"
                        onClick={crumb.onClick}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          fontSize: 'var(--fn-text-12)',
                          color: 'var(--ink-secondary)',
                          cursor: 'pointer',
                          textDecoration: 'none',
                        }}
                      >
                        {crumb.label}
                      </button>
                    ) : (
                      <span
                        style={{
                          color: isLast ? 'var(--ink)' : 'var(--ink-secondary)',
                          fontWeight: isLast ? 600 : 400,
                        }}
                        aria-current={isLast ? 'page' : undefined}
                      >
                        {crumb.label}
                      </span>
                    )}
                  </React.Fragment>
                )
              })}
            </nav>
          )}
        </div>

        {/* Right side controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Design System Preview link / toggle */}
          {import.meta.env.DEV && showDesignLink && onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate(currentRoute === 'design' ? 'app' : 'design')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                height: '28px',
                padding: '0 8px',
                borderRadius: 'var(--fn-radius-sm)',
                border: `1px solid ${currentRoute === 'design' ? 'var(--accent)' : 'var(--border)'}`,
                backgroundColor: currentRoute === 'design' ? 'var(--accent-bg)' : 'transparent',
                color: currentRoute === 'design' ? 'var(--accent)' : 'var(--ink-secondary)',
                fontSize: 'var(--fn-text-12)',
                fontWeight: 500,
                cursor: 'pointer',
              }}
              title="Design system tokens &amp; UI primitives"
            >
              <LayoutGrid size={13} aria-hidden="true" />
              <span>{currentRoute === 'design' ? 'Exit Design' : '/design'}</span>
            </button>
          )}

          {/* Light / Dark Theme Switcher */}
          <button
            type="button"
            onClick={toggleTheme}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '28px',
              height: '28px',
              borderRadius: 'var(--fn-radius-sm)',
              border: '1px solid var(--border)',
              backgroundColor: 'transparent',
              color: 'var(--ink-secondary)',
              cursor: 'pointer',
              transition: 'all var(--fn-motion-hover)',
            }}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
            title={`Current: ${theme} theme. Click to toggle.`}
          >
            {theme === 'light' ? <Moon size={14} aria-hidden="true" /> : <Sun size={14} aria-hidden="true" />}
          </button>
        </div>
      </header>

      {serviceWarning && (
        <div role="alert" aria-label="Service degraded" className="fn-service-banner">
          <strong>Degraded mode.</strong> {serviceWarning}
        </div>
      )}

      {/* Main Content Area */}
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  )
}
