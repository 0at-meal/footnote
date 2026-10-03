import React, { useState } from 'react'
import {
  Button,
  Input,
  Select,
  Badge,
  StatusDot,
  Tooltip,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Progress,
  Skeleton,
  DataTable,
} from '../ui'
import { Wordmark } from '../brand/Wordmark'
import { SourceChip } from '../brand/SourceChip'
import { contrastRatio, formatRatio, meetsAA } from '../../lib/contrast'
import { EmptyState } from '../brand/EmptyState'
import { CheckCircle2, ArrowRight, DollarSign, Search } from 'lucide-react'

/** Token pairs checked on this page; ratios are computed at render time (AUD-017). */
const CONTRAST_PAIRS: { name: string; fg: string; bg: string; kind: 'text' | 'large-or-ui' }[] = [
  { name: 'Light: ink on canvas', fg: '#14120F', bg: '#FAF8F4', kind: 'text' },
  { name: 'Light: muted ink on canvas', fg: '#6B665E', bg: '#FAF8F4', kind: 'text' },
  { name: 'Light: warn text on canvas', fg: '#B7791F', bg: '#FAF8F4', kind: 'text' },
  { name: 'Light: ok text on canvas', fg: '#1F8A5B', bg: '#FAF8F4', kind: 'text' },
  { name: 'Light: white on accent button', fg: '#FFFFFF', bg: '#2B4BEE', kind: 'text' },
  { name: 'Dark: ink on canvas', fg: '#ECEAE5', bg: '#0E0F12', kind: 'text' },
  { name: 'Dark: muted ink on canvas', fg: '#9A978F', bg: '#0E0F12', kind: 'text' },
  { name: 'Dark: white on accent button', fg: '#FFFFFF', bg: '#7B93FF', kind: 'text' },
]

export const DesignPreviewPage: React.FC = () => {
  const [btnLoading, setBtnLoading] = useState(false)
  const [inputValue, setInputValue] = useState('1,250,400.00')
  const [chipClickedInfo, setChipClickedInfo] = useState<string | null>(null)

  const sampleTableData = [
    { id: '1', metric: 'Reported Operating Income', value: '$1,250,400.00', period: 'FY2023', status: 'confirmed' },
    { id: '2', metric: 'Depreciation & Amortization', value: '$340,200.00', period: 'FY2023', status: 'confirmed' },
    { id: '3', metric: 'Restructuring Charges', value: '$45,800.00', period: 'FY2023', status: 'flagged' },
    { id: '4', metric: 'Stock-Based Compensation', value: '$112,000.00', period: 'FY2023', status: 'confirmed' },
    { id: '5', metric: 'Adjusted EBITDA', value: '$1,748,400.00', period: 'FY2023', status: 'auto_accepted' },
  ]

  const tableColumns = [
    { key: 'metric', header: 'Reconciliation Line Item', width: '45%' },
    { key: 'period', header: 'Period', width: '15%' },
    {
      key: 'status',
      header: 'Audit Status',
      width: '20%',
      render: (item: (typeof sampleTableData)[0]) => (
        <Badge
          variant={item.status === 'flagged' ? 'warn' : 'ok'}
          dot
          size="sm"
        >
          {item.status.replace('_', ' ')}
        </Badge>
      ),
    },
    {
      key: 'value',
      header: 'Amount ($)',
      isNumeric: true,
      align: 'right' as const,
      width: '20%',
      render: (item: (typeof sampleTableData)[0]) => (
        <span style={{ fontWeight: item.metric.includes('Adjusted') ? 700 : 500 }}>
          {item.value}
        </span>
      ),
    },
  ]

  return (
    <div
      style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '32px 24px 64px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '40px',
      }}
    >
      {/* Title & Introduction */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <Wordmark size="lg" />
          <span
            style={{
              padding: '2px 8px',
              borderRadius: 'var(--fn-radius-pill)',
              backgroundColor: 'var(--accent-bg)',
              color: 'var(--accent)',
              fontSize: '11px',
              fontWeight: 600,
              fontFamily: 'var(--fn-font-mono)',
            }}
          >
            Design System 1.0 (FN-061 &amp; FN-066)
          </span>
        </div>
        <p style={{ fontSize: 'var(--fn-text-14)', color: 'var(--ink-secondary)', margin: 0 }}>
          Specification-compliant primitives, design tokens, tabular typography, and brand system.
          Designed for compliance-grade financial statement review.
        </p>
      </div>

      <Tabs defaultValue="primitives">
        <TabsList>
          <TabsTrigger value="primitives">UI Primitives</TabsTrigger>
          <TabsTrigger value="tokens">Design Tokens &amp; Swatches</TabsTrigger>
          <TabsTrigger value="brand">Brand &amp; Markers (FN-066)</TabsTrigger>
          <TabsTrigger value="typography">Typography &amp; Tabular Figures</TabsTrigger>
          <TabsTrigger value="accessibility">WCAG AA Contrast Audit</TabsTrigger>
        </TabsList>

        {/* ── TAB 1: UI PRIMITIVES ── */}
        <TabsContent value="primitives" style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Buttons */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Buttons (.fn-btn)</CardTitle>
                <CardDescription>
                  Single primary action per screen. Strict hierarchical sizing (sm, md, lg).
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
                <Button variant="primary">Primary Action</Button>
                <Button variant="secondary">Secondary Action</Button>
                <Button variant="outline">Outline Action</Button>
                <Button variant="ghost">Ghost Button</Button>
                <Button variant="destructive">Destructive Action</Button>
                <Button
                  variant="primary"
                  isLoading={btnLoading}
                  onClick={() => {
                    setBtnLoading(true)
                    setTimeout(() => setBtnLoading(false), 1500)
                  }}
                >
                  {btnLoading ? 'Saving...' : 'Click for Loading State'}
                </Button>
                <Button variant="secondary" disabled>
                  Disabled Button
                </Button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
                <Button size="sm" variant="secondary">Small (28px)</Button>
                <Button size="md" variant="secondary">Medium (36px)</Button>
                <Button size="lg" variant="primary" rightIcon={<ArrowRight size={16} />}>
                  Large (42px) with Icon
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Form Controls: Input & Select */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Form Controls</CardTitle>
                <CardDescription>Accessible inputs with labels, helper text, and validation states.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
                <Input
                  label="Search Filings"
                  placeholder="e.g. AAPL 10-K..."
                  leftAddon={<Search size={14} />}
                />
                <Input
                  label="Financial Value ($)"
                  tabularNums
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  leftAddon={<DollarSign size={14} />}
                  helperText="Tabular numerals active for financial precision"
                />
                <Input
                  label="Invalid Entry Example"
                  value="N/A (unparseable)"
                  error="Raw string cannot be resolved to a numeric line item"
                  readOnly
                />
                <Select
                  label="Fiscal Year"
                  options={[
                    { value: '2025', label: 'FY 2025' },
                    { value: '2024', label: 'FY 2024' },
                    { value: '2023', label: 'FY 2023' },
                  ]}
                />
              </div>
            </CardContent>
            <CardFooter>
              <Button size="sm" variant="ghost">Reset Form</Button>
              <Tooltip content="Saves active inputs to temporary session" position="top">
                <Button size="sm" variant="primary">Save Changes</Button>
              </Tooltip>
            </CardFooter>
          </Card>

          {/* Badges & Status Signals */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Status Signals &amp; Badges</CardTitle>
                <CardDescription>
                  Restrained semantic badges (never color alone; includes text label and dot).
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                <Badge variant="ok" dot>Confirmed (Pass)</Badge>
                <Badge variant="warn" dot pulse>Needs Review (Flagged)</Badge>
                <Badge variant="danger" dot>Extraction Error</Badge>
                <Badge variant="neutral" dot>Queued / Pending</Badge>
                <Badge variant="accent">Model Ready</Badge>
                <Badge variant="ok" size="sm">Small Badge</Badge>
              </div>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <span style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>Status Dots:</span>
                <StatusDot status="ok" size="lg" />
                <StatusDot status="warn" size="lg" pulse />
                <StatusDot status="danger" size="lg" />
                <StatusDot status="neutral" size="lg" />
                <StatusDot status="accent" size="lg" />
              </div>
            </CardContent>
          </Card>

          {/* Progress & Skeletons */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Feedback: Progress &amp; Skeletons</CardTitle>
                <CardDescription>Loading states conforming to zero-motion fallback.</CardDescription>
              </div>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '12px' }}>
                  <span>Batch Extraction Progress</span>
                  <span className="tabular-nums">68%</span>
                </div>
                <Progress value={68} variant="accent" />
              </div>
              <div>
                <div style={{ marginBottom: '6px', fontSize: '12px' }}>Indeterminate Extraction Spinner</div>
                <Progress variant="warn" />
              </div>
              <div>
                <div style={{ marginBottom: '8px', fontSize: '12px' }}>Skeleton Loading Placeholders</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <Skeleton width="40%" height={20} />
                  <Skeleton width="100%" height={14} />
                  <Skeleton width="80%" height={14} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* DataTable Shell */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>DataTable Shell (FN-061)</CardTitle>
                <CardDescription>
                  Tabular numeral columns, right-aligned values, and zebra rows.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <DataTable
                columns={tableColumns}
                data={sampleTableData}
                keyExtractor={(item) => item.id}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 2: DESIGN TOKENS ── */}
        <TabsContent value="tokens" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <Card>
            <CardHeader>
              <CardTitle>Appendix A: Color Tokens (CSS Variables)</CardTitle>
              <CardDescription>
                Light-first &ldquo;Paper &amp; Ink&rdquo; palette with designed low-glare dark workstation theme.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--bg)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong>--bg</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Canvas</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--surface)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong>--surface</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Document / Panel</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong>--surface-2</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Elevated Header</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--accent)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong style={{ color: 'var(--accent)' }}>--accent</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Interaction Cobalt</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--highlight)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong style={{ color: '#854D0E' }}>--highlight</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Filing Citation Yellow</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--ok)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong style={{ color: 'var(--ok)' }}>--ok</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Pass / Confirmed</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--warn)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong style={{ color: 'var(--warn)' }}>--warn</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Needs Review</div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)', overflow: 'hidden' }}>
                  <div style={{ height: '60px', backgroundColor: 'var(--danger)', borderBottom: '1px solid var(--border)' }} />
                  <div style={{ padding: '8px 10px', fontSize: '12px' }}>
                    <strong style={{ color: 'var(--danger)' }}>--danger</strong>
                    <div style={{ color: 'var(--ink-muted)' }}>Discrepancy / Error</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Motion Tokens */}
          <Card>
            <CardHeader>
              <CardTitle>Motion Specification (Appendix A)</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <strong>150ms Hover</strong>
                  <div style={{ color: 'var(--ink-muted)', fontSize: '12px', marginTop: '4px' }}>
                    Button &amp; row background hover transitions.
                  </div>
                </div>
                <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <strong>200ms State</strong>
                  <div style={{ color: 'var(--ink-muted)', fontSize: '12px', marginTop: '4px' }}>
                    Modal, dropdown, popover appearances.
                  </div>
                </div>
                <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <strong>280ms Spring</strong>
                  <div style={{ color: 'var(--ink-muted)', fontSize: '12px', marginTop: '4px' }}>
                    Slide-over panels &amp; drawers (cubic-bezier(0.16, 1, 0.3, 1)).
                  </div>
                </div>
                <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <strong>Zero-Motion Fallback</strong>
                  <div style={{ color: 'var(--ink-muted)', fontSize: '12px', marginTop: '4px' }}>
                    @media (prefers-reduced-motion) overrides durations to 0.01ms.
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 3: BRAND & MARKERS (FN-066) ── */}
        <TabsContent value="brand" style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Wordmark */}
          <Card>
            <CardHeader>
              <CardTitle>Footnote Wordmark System</CardTitle>
              <CardDescription>
                Display serif brand with cobalt superscript footnote marker.
              </CardDescription>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--ink-muted)', marginBottom: '4px' }}>Small (16px)</div>
                  <Wordmark size="sm" />
                </div>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--ink-muted)', marginBottom: '4px' }}>Medium (22px)</div>
                  <Wordmark size="md" />
                </div>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--ink-muted)', marginBottom: '4px' }}>Large (32px)</div>
                  <Wordmark size="lg" />
                </div>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--ink-muted)', marginBottom: '4px' }}>Numbered Marker</div>
                  <Wordmark size="md" marker="¹" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* SourceChip Showcase */}
          <Card>
            <CardHeader>
              <CardTitle>SourceChip Citation Component</CardTitle>
              <CardDescription>
                Clickable footnote marker attached to extracted/modeled figures. Hover displays filing quote, click triggers PDF jump.
              </CardDescription>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div
                style={{
                  padding: '16px',
                  backgroundColor: 'var(--surface-2)',
                  borderRadius: 'var(--fn-radius-md)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '15px',
                }}
              >
                <span>Stock-Based Compensation Adjustment:</span>
                <strong className="tabular-nums">$75.00M</strong>
                <SourceChip
                  sourceFile="aapl-20230930.pdf"
                  page={42}
                  label="Stock-based compensation expense"
                  value="$75.00M"
                  snippet="Share-based compensation expense recognized within selling, general and administrative was $75 million for the fiscal year ended September 30, 2023."
                  onJumpToSource={(p) => setChipClickedInfo(`Jumped to PDF Page ${p} for aapl-20230930.pdf`)}
                />
              </div>

              {chipClickedInfo && (
                <div
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--fn-radius-sm)',
                    backgroundColor: 'var(--ok-bg)',
                    border: '1px solid var(--ok-border)',
                    color: 'var(--ok)',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <CheckCircle2 size={14} />
                  <span>{chipClickedInfo}</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Empty States (All 3 Variants) */}
          <Card>
            <CardHeader>
              <CardTitle>Three Actionable Empty States</CardTitle>
              <CardDescription>
                Tailored visual illustrations with contextual recovery actions.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
                <EmptyState
                  variant="no-filings"
                  onAction={() => alert('Action: Upload Filing clicked')}
                />
                <EmptyState
                  variant="no-items"
                  onAction={() => alert('Action: Return to Queue clicked')}
                />
                <EmptyState
                  variant="no-model"
                  onAction={() => alert('Action: Generate Model clicked')}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 4: TYPOGRAPHY & TABULAR FIGURES ── */}
        <TabsContent value="typography" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <Card>
            <CardHeader>
              <CardTitle>Tabular Numerals Comparison</CardTitle>
              <CardDescription>
                Proportional figures wiggle and misalign across columns. Tabular figures maintain monospace digit widths for financial precision.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                <div style={{ padding: '16px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--danger)', marginBottom: '8px', fontSize: '13px' }}>
                    Proportional Figures (Flawed alignment)
                  </div>
                  <div style={{ fontFamily: 'var(--fn-font-sans)', fontSize: '18px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div>1,111,111.11</div>
                    <div>8,888,888.88</div>
                    <div>2,345,678.90</div>
                    <div>1,000,000.00</div>
                  </div>
                </div>

                <div style={{ padding: '16px', border: '1px solid var(--border)', borderRadius: 'var(--fn-radius-sm)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--ok)', marginBottom: '8px', fontSize: '13px' }}>
                    Tabular Figures (font-variant-numeric: tabular-nums)
                  </div>
                  <div
                    className="tabular-nums"
                    style={{ fontFamily: 'var(--fn-font-sans)', fontSize: '18px', display: 'flex', flexDirection: 'column', gap: '4px' }}
                  >
                    <div>1,111,111.11</div>
                    <div>8,888,888.88</div>
                    <div>2,345,678.90</div>
                    <div>1,000,000.00</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 5: WCAG AA CONTRAST AUDIT ── */}
        <TabsContent value="accessibility" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <Card>
            <CardHeader>
              <CardTitle>WCAG 2.1 AA Contrast Ratio Verification</CardTitle>
              <CardDescription>
                Required minimum: 4.5:1 for standard text, 3:1 for large text and interactive boundaries.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {CONTRAST_PAIRS.map((pair) => {
                  const ratio = contrastRatio(pair.fg, pair.bg)
                  const ok = meetsAA(ratio, pair.kind)
                  return (
                    <div
                      key={pair.name}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', borderBottom: '1px solid var(--border)' }}
                    >
                      <div>
                        <strong>{pair.name}</strong>
                        <div style={{ fontSize: '12px', color: 'var(--ink-muted)' }}>
                          {pair.fg} on {pair.bg} ({pair.kind === 'text' ? 'text, needs 4.5:1' : 'large text / UI, needs 3:1'})
                        </div>
                      </div>
                      <Badge variant={ok ? 'ok' : 'danger'}>
                        {formatRatio(ratio)} ({ok ? 'PASS' : 'FAIL'} AA)
                      </Badge>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
