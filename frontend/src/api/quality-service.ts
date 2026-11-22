/** 治理看板指标接口：新样本口径重算、两轮回查、整改同步与回执核对。 */
import { request } from './client'
import type {
  Comparison,
  DashboardPayload,
  ReceiptVerification,
  RemediationPlan,
  RoundMetrics,
  ScopeKey,
  SyncResult,
} from '@/domain/govern_dash'

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}，指标未更新`)
  return (await response.json()) as T
}

export function loadGovernDashboard(round = 2, baseline = 1): Promise<DashboardPayload> {
  return getJson<DashboardPayload>(`/api/quality/dashboard?round=${round}&baseline=${baseline}`)
}

export function loadMetrics(round = 2, scope: ScopeKey = 'expanded'): Promise<RoundMetrics> {
  return getJson<RoundMetrics>(`/api/quality/metrics?round=${round}&scope=${scope}`)
}

export function loadComparison(baseline = 1, current = 2): Promise<Comparison> {
  return getJson<Comparison>(`/api/quality/compare?baseline=${baseline}&current=${current}`)
}

export function loadRemediation(round = 2, scope: ScopeKey = 'expanded'): Promise<RemediationPlan> {
  return getJson<RemediationPlan>(`/api/quality/remediation?round=${round}&scope=${scope}`)
}

export async function syncRemediation(
  round = 2,
  scope: ScopeKey = 'expanded',
  remark = '治理看板',
): Promise<SyncResult> {
  const response = await request(
    `/api/quality/remediation/sync?round=${round}&scope=${scope}&operator=${encodeURIComponent(remark)}`,
    { method: 'POST', body: JSON.stringify({ action: '同步整改', remark }) },
  )
  const payload = (await response.json()) as SyncResult | { detail?: string }
  if (!response.ok) {
    throw new Error('detail' in payload && payload.detail ? payload.detail : '整改清单同步失败')
  }
  const result = payload as SyncResult
  if (!result.ok) throw new Error(result.message)
  return result
}

export function verifyReceipt(receiptId: string): Promise<ReceiptVerification> {
  return getJson<ReceiptVerification>(`/api/quality/receipts/${encodeURIComponent(receiptId)}`)
}
