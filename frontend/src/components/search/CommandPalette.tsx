import React, { useState, useEffect, useRef } from 'react'
import { Search, Building, FileUp, Sparkles, X } from 'lucide-react'
import type { CompanyWithJobs } from '../../types/job'

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  companies: CompanyWithJobs[]
  onSelectCompany: (companyName: string) => void
  onUploadClick: () => void
}

export function CommandPalette({
  isOpen,
  onClose,
  companies,
  onSelectCompany,
  onUploadClick,
}: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Global ⌘K / Ctrl+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (isOpen) {
          onClose()
        } else {
          // Open handled by parent or state
        }
      } else if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  // Items to search: Actions + Companies
  const actionItems = [
    {
      id: 'action-upload',
      type: 'action' as const,
      label: 'Upload a filing (PDF 10-K / 10-Q)',
      action: () => {
        onUploadClick()
        onClose()
      },
    },
  ]

  const companyItems = companies
    .filter(
      (c) =>
        c.name.toLowerCase().includes(query.toLowerCase()) ||
        (c.ticker && c.ticker.toLowerCase().includes(query.toLowerCase())),
    )
    .map((c) => ({
      id: `company-${c.company_id}`,
      type: 'company' as const,
      label: c.ticker ? `${c.ticker} · ${c.name}` : c.name,
      company: c,
      action: () => {
        onSelectCompany(c.name)
        onClose()
      },
    }))

  const allItems = [...actionItems, ...companyItems]

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, allItems.length))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev - 1 + allItems.length) % Math.max(1, allItems.length))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (allItems[selectedIndex]) {
        allItems[selectedIndex].action()
      }
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette and ticker search"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        backgroundColor: 'rgba(20, 18, 15, 0.45)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '12vh',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          backgroundColor: 'var(--surface)',
          borderRadius: 'var(--fn-radius-lg)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--fn-shadow-lg)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search Input Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            backgroundColor: 'var(--surface)',
          }}
        >
          <Search size={18} style={{ color: 'var(--ink-muted)' }} aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelectedIndex(0)
            }}
            placeholder="Search ticker, company, or action... (e.g. AAPL)"
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              background: 'transparent',
              fontSize: 'var(--fn-text-14)',
              color: 'var(--ink)',
              fontFamily: 'var(--fn-font-sans)',
            }}
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close command palette"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-muted)',
              padding: '2px',
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: '320px', overflowY: 'auto', padding: '8px' }}>
          {allItems.length === 0 ? (
            <div
              style={{
                padding: '24px 16px',
                textAlign: 'center',
                color: 'var(--ink-muted)',
                fontSize: 'var(--fn-text-13)',
              }}
            >
              No matching companies or actions found for "{query}"
            </div>
          ) : (
            allItems.map((item, idx) => {
              const isSelected = idx === selectedIndex
              return (
                <div
                  key={item.id}
                  onClick={item.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    borderRadius: 'var(--fn-radius-md)',
                    backgroundColor: isSelected ? 'var(--surface-2)' : 'transparent',
                    cursor: 'pointer',
                    transition: 'background-color var(--fn-motion-hover)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {item.type === 'company' ? (
                      <Building size={16} style={{ color: 'var(--accent)' }} aria-hidden="true" />
                    ) : (
                      <FileUp size={16} style={{ color: 'var(--ok)' }} aria-hidden="true" />
                    )}
                    <span
                      style={{
                        fontSize: 'var(--fn-text-13)',
                        fontWeight: item.type === 'company' ? 600 : 500,
                        color: 'var(--ink)',
                      }}
                    >
                      {item.label}
                    </span>
                  </div>
                  {item.type === 'company' && item.company.jobs && (
                    <span
                      style={{
                        fontSize: '11px',
                        color: 'var(--ink-muted)',
                      }}
                    >
                      {item.company.jobs.length} filing{item.company.jobs.length === 1 ? '' : 's'}
                    </span>
                  )}
                  {item.type === 'action' && (
                    <span
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '11px',
                        color: 'var(--ink-muted)',
                      }}
                    >
                      <Sparkles size={11} aria-hidden="true" /> Action
                    </span>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div
          style={{
            padding: '8px 16px',
            backgroundColor: 'var(--surface-2)',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '11px',
            color: 'var(--ink-muted)',
          }}
        >
          <span>Use ↑/↓ to navigate, Enter to select</span>
          <span>Esc to exit</span>
        </div>
      </div>
    </div>
  )
}
