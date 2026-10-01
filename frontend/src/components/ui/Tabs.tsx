import React, { createContext, useContext, useState } from 'react'

interface TabsContextValue {
  activeTab: string
  setActiveTab: (val: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

export interface TabsProps {
  defaultValue: string
  value?: string
  onValueChange?: (val: string) => void
  children: React.ReactNode
  className?: string
}

export const Tabs: React.FC<TabsProps> = ({
  defaultValue,
  value,
  onValueChange,
  children,
  className = '',
}) => {
  const [internalTab, setInternalTab] = useState(defaultValue)
  const activeTab = value !== undefined ? value : internalTab

  const handleTabChange = (val: string) => {
    if (value === undefined) {
      setInternalTab(val)
    }
    onValueChange?.(val)
  }

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab: handleTabChange }}>
      <div className={`fn-tabs ${className}`} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

export const TabsList: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  style,
  ...props
}) => {
  return (
    <div
      role="tablist"
      className={`fn-tabs-list ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px',
        backgroundColor: 'var(--surface-2)',
        borderRadius: 'var(--fn-radius-sm)',
        border: '1px solid var(--border)',
        gap: '2px',
        width: 'fit-content',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  )
}

export interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string
}

export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  value,
  children,
  className = '',
  style,
  ...props
}) => {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('TabsTrigger must be used within Tabs')

  const isActive = ctx.activeTab === value

  return (
    <button
      role="tab"
      type="button"
      aria-selected={isActive}
      className={`fn-tab-trigger ${className}`}
      onClick={() => ctx.setActiveTab(value)}
      style={{
        padding: '5px 12px',
        fontSize: 'var(--fn-text-13)',
        fontWeight: isActive ? 600 : 500,
        color: isActive ? 'var(--ink)' : 'var(--ink-secondary)',
        backgroundColor: isActive ? 'var(--surface)' : 'transparent',
        borderRadius: 'calc(var(--fn-radius-sm) - 2px)',
        border: 'none',
        boxShadow: isActive ? 'var(--fn-shadow-sm)' : 'none',
        cursor: 'pointer',
        transition: 'all var(--fn-motion-hover)',
        ...style,
      }}
      {...props}
    >
      {children}
    </button>
  )
}

export interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string
}

export const TabsContent: React.FC<TabsContentProps> = ({
  value,
  children,
  className = '',
  style,
  ...props
}) => {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('TabsContent must be used within Tabs')

  if (ctx.activeTab !== value) return null

  return (
    <div
      role="tabpanel"
      className={`fn-tab-content ${className}`}
      style={{
        outline: 'none',
        animation: 'fn-tab-appear var(--fn-motion-state)',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  )
}
