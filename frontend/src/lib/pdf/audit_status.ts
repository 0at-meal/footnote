import type { SourceComponent } from '../../types/audit'

export type ChainStatusRollup = {
  kind: 'all_locked' | 'contains_flagged' | 'has_missing' | 'in_review'
  label: string
  detail: string
  badgeClass: string
}

export function computeChainRollup(components: SourceComponent[]): ChainStatusRollup {
  if (components.length === 0) {
    return {
      kind: 'in_review',
      label: 'No Source Records',
      detail: '0 records in chain',
      badgeClass: 'status-badge--pending',
    }
  }

  const missingCount = components.filter(
    (c) => c.is_missing || c.review_status === 'source_record_missing',
  ).length
  if (missingCount > 0) {
    return {
      kind: 'has_missing',
      label: `Missing Records (${missingCount}/${components.length})`,
      detail: 'One or more source records were deleted',
      badgeClass: 'status-badge--failed',
    }
  }

  const flaggedCount = components.filter((c) => c.review_status === 'flagged').length
  if (flaggedCount > 0) {
    return {
      kind: 'contains_flagged',
      label: `Flagged (${flaggedCount}/${components.length})`,
      detail: `${flaggedCount} component(s) flagged during review`,
      badgeClass: 'status-badge--extracting',
    }
  }

  const lockedCount = components.filter((c) => c.review_status === 'locked').length
  if (lockedCount === components.length) {
    return {
      kind: 'all_locked',
      label: `All Verified (${lockedCount}/${components.length})`,
      detail: 'All contributing components verified & locked',
      badgeClass: 'status-badge--done',
    }
  }

  return {
    kind: 'in_review',
    label: `In Review (${lockedCount}/${components.length} Locked)`,
    detail: 'Pending analyst review and confirmation',
    badgeClass: 'status-badge--queued',
  }
}
