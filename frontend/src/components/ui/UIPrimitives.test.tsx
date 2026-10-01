import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Button,
  Input,
  Select,
  Badge,
  StatusDot,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Progress,
  Skeleton,
  DataTable,
} from './index'

describe('UI Primitives (FN-061)', () => {
  it('renders Button with variants, sizes, and loading spinner', () => {
    const primaryHtml = renderToStaticMarkup(<Button variant="primary">Confirm</Button>)
    expect(primaryHtml).toContain('fn-btn')
    expect(primaryHtml).toContain('fn-btn--primary')
    expect(primaryHtml).toContain('Confirm')

    const loadingHtml = renderToStaticMarkup(
      <Button variant="secondary" isLoading size="sm">
        Save
      </Button>,
    )
    expect(loadingHtml).toContain('animate-spin')
    expect(loadingHtml).toContain('fn-btn--sm')
    expect(loadingHtml).toContain('disabled=""')
  })

  it('renders Input with labels, helperText, and error states', () => {
    const inputHtml = renderToStaticMarkup(
      <Input
        label="Adjusted EBITDA"
        tabularNums
        defaultValue="1,200.00"
        error="Invalid figure"
      />,
    )
    expect(inputHtml).toContain('Adjusted EBITDA')
    expect(inputHtml).toContain('tabular-nums')
    expect(inputHtml).toContain('Invalid figure')
    expect(inputHtml).toContain('aria-invalid="true"')
  })

  it('renders Select with options', () => {
    const selectHtml = renderToStaticMarkup(
      <Select
        label="Year"
        options={[
          { value: '2023', label: 'FY2023' },
          { value: '2024', label: 'FY2024' },
        ]}
      />,
    )
    expect(selectHtml).toContain('Year')
    expect(selectHtml).toContain('FY2023')
    expect(selectHtml).toContain('FY2024')
  })

  it('renders Badge and StatusDot with semantic signals', () => {
    const badgeHtml = renderToStaticMarkup(
      <Badge variant="ok" dot>
        Model Ready
      </Badge>,
    )
    expect(badgeHtml).toContain('status-badge--ok')
    expect(badgeHtml).toContain('fn-status-dot--ok')
    expect(badgeHtml).toContain('Model Ready')

    const dotHtml = renderToStaticMarkup(<StatusDot status="warn" pulse />)
    expect(dotHtml).toContain('fn-status-dot--warn')
  })

  it('renders Card suite', () => {
    const cardHtml = renderToStaticMarkup(
      <Card elevated>
        <CardHeader>
          <CardTitle>Reconciliation Model</CardTitle>
        </CardHeader>
        <CardContent>
          <p>Model content</p>
        </CardContent>
        <CardFooter>
          <Button size="sm">Download</Button>
        </CardFooter>
      </Card>,
    )
    expect(cardHtml).toContain('fn-card')
    expect(cardHtml).toContain('Reconciliation Model')
    expect(cardHtml).toContain('Model content')
    expect(cardHtml).toContain('Download')
  })

  it('renders Tabs with active content', () => {
    const tabsHtml = renderToStaticMarkup(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Overview</TabsTrigger>
          <TabsTrigger value="tab2">Details</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Overview Content</TabsContent>
        <TabsContent value="tab2">Details Content</TabsContent>
      </Tabs>,
    )
    expect(tabsHtml).toContain('Overview')
    expect(tabsHtml).toContain('Overview Content')
    expect(tabsHtml).not.toContain('Details Content')
  })

  it('renders Progress and Skeleton components', () => {
    const progressHtml = renderToStaticMarkup(<Progress value={75} max={100} />)
    expect(progressHtml).toContain('aria-valuenow="75"')
    expect(progressHtml).toContain('width:75%')

    const skeletonHtml = renderToStaticMarkup(<Skeleton width="200px" height="20px" />)
    expect(skeletonHtml).toContain('fn-skeleton')
  })

  it('renders DataTable with tabular numeral cells and alignment', () => {
    const columns = [
      { key: 'item', header: 'Line Item' },
      { key: 'amount', header: 'Amount ($)', isNumeric: true, align: 'right' as const },
    ]
    const data = [
      { id: '1', item: 'Operating Income', amount: '1,500.00' },
      { id: '2', item: 'D&A', amount: '350.00' },
    ]

    const tableHtml = renderToStaticMarkup(
      <DataTable
        columns={columns}
        data={data}
        keyExtractor={(d) => d.id}
      />,
    )

    expect(tableHtml).toContain('Operating Income')
    expect(tableHtml).toContain('1,500.00')
    expect(tableHtml).toContain('font-variant-numeric:tabular-nums')
    expect(tableHtml).toContain('text-align:right')
  })
})
