/** 可复核质量指标的数据契约与口径说明（与后端 /api/quality 对齐）。 */

export type StratumKey = 'overlap' | 'new' | 'all'
export type ScopeKey = 'expanded' | 'overlap'

export type StratumMetric = {
  stratum: StratumKey
  label: string
  entity_count: number
  sample_count: number
  entity_ids: string[]
  sample_ids: string[]
  numerator: number
  denominator: number
  error_rate_pct: number | null
  numerator_detail_backed: number
  numerator_without_detail: number
  detail_coverage_pct: number | null
  detail_refs: string[]
  missing_detail_refs: string[]
  graph_versions: string[]
}

export type RoundMetrics = {
  round: number
  round_label: string
  graph_version: string
  audit_date: string
  scope: ScopeKey
  scope_label: string
  available: boolean
  unavailable_reason: string | null
  missing_sample_ids: string[]
  strata: StratumMetric[]
  total: StratumMetric
  generated_at: string
}

export type MatchedComparison = {
  status: string
  entity_ids: string[]
  baseline: StratumMetric
  current: StratumMetric
  baseline_error_rate_pct: number
  current_error_rate_pct: number
  improvement_pp: number
  improvement_rate_pct: number | null
  direction: string
}

export type ExpandedComparison = {
  status: 'comparable' | 'not_comparable'
  reason: string
  baseline: StratumMetric
  current: StratumMetric
  delta_pp: number | null
  improvement_rate_pct: number | null
  direction: string
  display_only?: boolean
}

export type Comparison = {
  baseline: { round: number; label: string; graph_version: string; available: boolean; unavailable_reason: string | null }
  current: { round: number; label: string; graph_version: string; available: boolean; unavailable_reason: string | null }
  status: 'ok' | 'baseline_missing' | 'no_common_sample'
  improvement_rate: number | null
  improvement_pp: number | null
  direction: string
  reason?: string
  guarded_fallback?: { attempted: string; allowed: boolean; reason: string }
  matched_same_scope?: MatchedComparison
  expanded_scope?: ExpandedComparison
  conflict?: {
    detected: boolean
    overlap_direction: string
    full_scope_direction: string
    full_scope_claimable: boolean
    note: string
  }
  current_scope_metrics?: RoundMetrics
  baseline_scope_metrics?: RoundMetrics | null
  generated_at: string
}

export type RemediationItem = {
  ref_id: string
  detail_id: string
  round: number
  sample_id: string
  entity_id: string
  entity_name: string
  stratum: StratumKey
  source_entity: string
  target_entity: string
  relation: string
  graph_version: string
  scope: ScopeKey
  status: string
}

export type SkippedMislink = {
  ref_id: string
  detail_id: string | null
  detail_available: false
  round: number
  sample_id: string
  entity_id: string
  stratum: StratumKey
  graph_version: string
  reason: string
}

export type RemediationPlan = {
  round: number
  scope: ScopeKey
  graph_version: string
  available: boolean
  unavailable_reason: string | null
  entity_ids: string[]
  sample_ids: string[]
  sampled_checked_links: number
  items: RemediationItem[]
  skipped: SkippedMislink[]
  counts: {
    dispatchable: number
    skipped_missing_detail: number
    by_stratum: Partial<Record<StratumKey, number>>
    numerator: number
    denominator: number
  }
  generated_at: string
}

export type Receipt = {
  receipt_id: string
  round: number
  scope: ScopeKey
  scope_label: string
  graph_version: string
  entity_ids: string[]
  sample_ids: string[]
  snapshot: {
    numerator: number
    denominator: number
    error_rate_pct: number | null
    dispatchable: number
    skipped_missing_detail: number
    graph_version: string
  }
  status: string
  accepted_at: string
  last_synced_at: string
  operator: string
}

export type SyncResult = {
  ok: boolean
  message: string
  receipt: Receipt | null
  items: RemediationItem[]
  skipped: SkippedMislink[]
  counts: RemediationPlan['counts']
}

export type DashboardPayload = {
  round: number
  baseline_round: number
  metrics: RoundMetrics
  legacy_scope_metrics: RoundMetrics
  baseline_metrics: RoundMetrics | null
  comparison: Comparison
  remediation_preview: {
    expanded: RemediationPlan['counts']
    overlap: RemediationPlan['counts']
  }
  receipts: Receipt[]
  generated_at: string
}

export type ReceiptVerification = {
  receipt_id: string
  status: string
  available: boolean
  reason?: string
  missing_sample_ids?: string[]
  graph_version?: string | string[]
  snapshot: Receipt['snapshot']
  recomputed: {
    numerator: number
    denominator: number
    error_rate_pct: number | null
    graph_version: string[]
    sample_ids: string[]
  } | null
  drift: { numerator: number; denominator: number; dispatchable: number } | null
  improvement_claim: null
}

export function formatRate(value: number | null | undefined): string {
  return value === null || value === undefined ? '不可计算' : `${value.toFixed(2)}%`
}

export function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined) return '不可比'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}pp`
}
