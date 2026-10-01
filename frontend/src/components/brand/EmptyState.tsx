import React from 'react'
import { FileUp, ListChecks, FileSpreadsheet } from 'lucide-react'
import { Button } from '../ui/Button'

export type EmptyStateVariant = 'no-filings' | 'no-items' | 'no-model'

export interface EmptyStateProps {
  variant: EmptyStateVariant
  title?: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  className?: string
  style?: React.CSSProperties
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  variant,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
  style,
}) => {
  const configs: Record<
    EmptyStateVariant,
    {
      icon: React.ReactNode
      defaultTitle: string
      defaultDesc: string
      defaultAction: string
    }
  > = {
    'no-filings': {
      icon: <FileUp size={36} style={{ color: 'var(--accent)' }} />,
      defaultTitle: 'No filings in processing queue',
      defaultDesc:
        'Upload 10-K or 10-Q SEC PDF filings above to extract non-GAAP reconciliations and financial footnotes.',
      defaultAction: 'Upload Filing',
    },
    'no-items': {
      icon: <ListChecks size={36} style={{ color: 'var(--ok)' }} />,
      defaultTitle: 'No line items requiring review',
      defaultDesc:
        'All extracted footnote items have been verified, or no candidate add-backs were detected in this filing.',
      defaultAction: 'Return to Queue',
    },
    'no-model': {
      icon: <FileSpreadsheet size={36} style={{ color: 'var(--warn)' }} />,
      defaultTitle: 'No financial model generated yet',
      defaultDesc:
        'Confirm the extracted adjustments above to compile the live-formula two-column Excel reconciliation workbook.',
      defaultAction: 'Generate Model',
    },
  }

  const current = configs[variant]
  const displayTitle = title || current.defaultTitle
  const displayDesc = description || current.defaultDesc
  const displayAction = actionLabel || current.defaultAction

  return (
    <div
      className={`fn-empty-state fn-empty-state--${variant} ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
        backgroundColor: 'var(--surface-2)',
        borderRadius: 'var(--fn-radius-md)',
        border: '1px dashed var(--border-strong)',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '64px',
          height: '64px',
          borderRadius: '50%',
          backgroundColor: 'var(--surface)',
          boxShadow: 'var(--fn-shadow-sm)',
          marginBottom: '16px',
        }}
      >
        {current.icon}
      </div>

      <h4
        style={{
          margin: '0 0 8px 0',
          fontSize: 'var(--fn-text-16)',
          fontWeight: 600,
          color: 'var(--ink)',
        }}
      >
        {displayTitle}
      </h4>

      <p
        style={{
          margin: '0 0 20px 0',
          maxWidth: '420px',
          fontSize: 'var(--fn-text-13)',
          color: 'var(--ink-muted)',
          lineHeight: 1.5,
        }}
      >
        {displayDesc}
      </p>

      {onAction && (
        <Button variant="primary" size="md" onClick={onAction}>
          {displayAction}
        </Button>
      )}
    </div>
  )
}
