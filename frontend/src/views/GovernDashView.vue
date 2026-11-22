<template>
  <section class="page govern-page" data-testid="govern-page">
    <header class="page-head">
      <div>
        <h2>治理看板 · 可复核质量指标</h2>
        <p class="page-desc">
          按审计取样分层聚合错连率：分子为判定错连的关系条数，分母为抽检关系条数，
          每个指标都带样本编号、实体清单与图谱版本，可逐条回查。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="reload" type="button" @click="reload">刷新指标</button>
        <button class="btn" data-testid="goto-audit" type="button" @click="router.push('/quality_audit')">
          查看审计报告
        </button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text" data-testid="error">{{ errorMessage }}</p>
    <p v-if="loading" class="status-legend">指标加载中…</p>

    <template v-if="dashboard">
      <!-- 口径选择：同一轮数据，两种样本范围 -->
      <div class="scope-tabs" data-testid="scope-tabs">
        <button
          v-for="option in scopeOptions"
          :key="option.scope"
          class="scope-tab"
          type="button"
          :class="{ active: scope === option.scope }"
          :data-testid="`scope-${option.scope}`"
          @click="selectScope(option.scope)"
        >
          {{ option.label }}
        </button>
      </div>

      <section class="metric-strip">
        <article class="stat-card" data-testid="stat-rate">
          <span class="stat-label">错连率（{{ currentMetrics.scope_label }}）</span>
          <strong class="stat-value">{{ formatRate(currentMetrics.total.error_rate_pct) }}</strong>
          <span class="stat-note">
            分子 {{ currentMetrics.total.numerator }} / 分母 {{ currentMetrics.total.denominator }}
          </span>
        </article>
        <article class="stat-card" data-testid="stat-samples">
          <span class="stat-label">取样实体</span>
          <strong class="stat-value">{{ currentMetrics.total.entity_count }}</strong>
          <span class="stat-note">重叠 {{ overlapEntityCount }} · 新增 {{ newEntityCount }}</span>
        </article>
        <article class="stat-card" data-testid="stat-improvement">
          <span class="stat-label">同口径改善率（{{ comparison.baseline.graph_version }} → {{ comparison.current.graph_version }}）</span>
          <strong class="stat-value">{{ formatRate(comparison.improvement_rate) }}</strong>
          <span class="stat-note">
            <template v-if="comparison.improvement_rate !== null">
              {{ comparison.matched_same_scope?.baseline_error_rate_pct }}% → {{ comparison.matched_same_scope?.current_error_rate_pct }}%
              （{{ formatDelta(comparison.improvement_pp) }}，{{ comparison.direction }}）
            </template>
            <template v-else>{{ comparison.direction }}</template>
          </span>
        </article>
        <article class="stat-card" data-testid="stat-dispatchable">
          <span class="stat-label">可派发整改（{{ scopeLabel }}）</span>
          <strong class="stat-value">{{ remediation?.counts.dispatchable ?? 0 }}</strong>
          <span class="stat-note">
            未落明细 {{ remediation?.counts.skipped_missing_detail ?? 0 }} 条不派发
          </span>
        </article>
      </section>

      <!-- 趋势冲突提示 -->
      <section
        v-if="comparison.conflict"
        class="callout"
        :class="comparison.conflict.detected ? 'warn' : 'ok'"
        data-testid="conflict-callout"
      >
        <strong>{{ comparison.conflict.detected ? '两种口径趋势相反' : '口径提示' }}</strong>
        <p>
          重叠样本口径：{{ comparison.conflict.overlap_direction }}；
          全量口径：{{ comparison.conflict.full_scope_direction }}
          <template v-if="!comparison.conflict.full_scope_claimable">
            （全量口径分子分母构成不同，只作展示，不能当作改善率）
          </template>
        </p>
        <p class="muted">{{ comparison.conflict.note }}</p>
      </section>

      <section
        v-if="comparison.status === 'baseline_missing'"
        class="callout danger"
        data-testid="baseline-missing"
      >
        <strong>基线样本缺失，改善率不可计算</strong>
        <p>{{ comparison.reason }}</p>
        <p class="muted">
          已拦截的替代算法：{{ comparison.guarded_fallback?.attempted }}（{{ comparison.guarded_fallback?.reason }}）。
          本期全量错连率 {{ formatRate(comparison.current_scope_metrics?.total.error_rate_pct) }} 仅代表本期，不作为改善依据。
        </p>
      </section>

      <!-- 分层指标表：分子、分母、版本、样本编号 -->
      <table class="data-table" data-testid="stratum-table">
        <thead>
          <tr>
            <th>分层</th>
            <th>取样实体</th>
            <th>分子（错连）</th>
            <th>分母（抽检关系）</th>
            <th>错连率</th>
            <th>有明细</th>
            <th>图谱版本</th>
            <th>样本编号</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stratum in currentMetrics.strata" :key="stratum.stratum" :data-testid="`stratum-${stratum.stratum}`">
            <td>{{ stratum.label }}</td>
            <td>{{ stratum.entity_count }}</td>
            <td>{{ stratum.numerator }}</td>
            <td>{{ stratum.denominator }}</td>
            <td>{{ formatRate(stratum.error_rate_pct) }}</td>
            <td>{{ stratum.numerator_detail_backed }} / {{ stratum.numerator }}</td>
            <td>{{ stratum.graph_versions.join('、') }}</td>
            <td class="mono">{{ stratum.sample_ids.join('、') }}</td>
          </tr>
        </tbody>
      </table>

      <!-- 两轮比较 -->
      <section class="panel" data-testid="comparison-panel">
        <h3>两轮审计比较（第 {{ comparison.baseline.round }} 轮 vs 第 {{ comparison.current.round }} 轮）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>比较项</th>
              <th>基线 {{ comparison.baseline.graph_version }}</th>
              <th>本期 {{ comparison.current.graph_version }}</th>
              <th>变化</th>
              <th>是否可作为改善率</th>
            </tr>
          </thead>
          <tbody>
            <tr data-testid="compare-matched">
              <td>同口径（两轮共同实体 {{ comparison.matched_same_scope?.entity_ids.length ?? 0 }} 个）</td>
              <td>{{ formatRate(comparison.matched_same_scope?.baseline_error_rate_pct) }}
                （{{ comparison.matched_same_scope?.baseline.numerator }}/{{ comparison.matched_same_scope?.baseline.denominator }}）</td>
              <td>{{ formatRate(comparison.matched_same_scope?.current_error_rate_pct) }}
                （{{ comparison.matched_same_scope?.current.numerator }}/{{ comparison.matched_same_scope?.current.denominator }}）</td>
              <td>{{ formatDelta(comparison.improvement_pp) }} · {{ comparison.direction }}</td>
              <td>是</td>
            </tr>
            <tr data-testid="compare-expanded">
              <td>扩围全量（{{ comparison.expanded_scope?.current.entity_count ?? 0 }} 个实体）</td>
              <td>{{ formatRate(comparison.expanded_scope?.baseline.error_rate_pct) }}
                （{{ comparison.expanded_scope?.baseline.numerator }}/{{ comparison.expanded_scope?.baseline.denominator }}）</td>
              <td>{{ formatRate(comparison.expanded_scope?.current.error_rate_pct) }}
                （{{ comparison.expanded_scope?.current.numerator }}/{{ comparison.expanded_scope?.current.denominator }}）</td>
              <td>{{ formatDelta(comparison.expanded_scope?.delta_pp) }} · {{ comparison.expanded_scope?.direction }}</td>
              <td>{{ comparison.expanded_scope?.status === 'comparable' ? '是' : '否（口径不可比）' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="muted">{{ comparison.expanded_scope?.reason }}</p>
      </section>

      <!-- 整改清单 -->
      <section class="panel" data-testid="remediation-panel">
        <div class="panel-head">
          <h3>整改清单（{{ remediation?.scope === 'expanded' ? '新样本口径' : '旧范围口径' }}）</h3>
          <button
            class="btn primary"
            data-testid="sync-remediation"
            type="button"
            :disabled="syncing"
            @click="sync"
          >
            {{ syncing ? '同步中…' : '同步取样结果到整改清单' }}
          </button>
        </div>
        <p class="muted">
          只有落到明细的错连才进入整改；当前 {{ remediation?.counts.dispatchable ?? 0 }} 条可派发，
          {{ remediation?.counts.skipped_missing_detail ?? 0 }} 条未落明细仅登记。
          取样实体 {{ remediation?.entity_ids.length ?? 0 }} 个，抽检关系 {{ remediation?.sampled_checked_links ?? 0 }} 条。
          <template v-if="remediation && !remediation.available">
            当前口径原样本不可取得（{{ remediation.unavailable_reason }}），清单为空，不代表错连已清零。
          </template>
        </p>
        <table class="data-table">
          <thead>
            <tr>
              <th>明细编号</th>
              <th>样本</th>
              <th>分层</th>
              <th>错连关系</th>
              <th>图谱版本</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in remediation?.items ?? []" :key="item.ref_id" :data-testid="`remediation-${item.ref_id}`">
              <td class="mono">{{ item.detail_id }}</td>
              <td>{{ item.entity_id }} · {{ item.entity_name }}</td>
              <td>{{ stratumLabel(item.stratum) }}</td>
              <td>{{ item.source_entity }} → {{ item.target_entity }}（{{ item.relation }}）</td>
              <td>{{ item.graph_version }}</td>
              <td>{{ item.status }}</td>
            </tr>
            <tr v-if="!(remediation?.items ?? []).length">
              <td colspan="6" class="empty-state">当前口径没有可派发的明细错连</td>
            </tr>
          </tbody>
        </table>
        <details v-if="remediation?.skipped.length" class="skipped-block">
          <summary>未落明细、不派发的错连 {{ remediation.skipped.length }} 条</summary>
          <ul>
            <li v-for="item in remediation.skipped" :key="item.ref_id" class="mono">
              {{ item.ref_id }} · {{ item.entity_id }} · {{ item.graph_version }} · {{ item.reason }}
            </li>
          </ul>
        </details>
        <p v-if="syncMessage" class="sync-message" data-testid="sync-message">{{ syncMessage }}</p>
      </section>

      <!-- 已受理范围回执 -->
      <section class="panel" data-testid="receipts-panel">
        <h3>已受理范围（可核对）</h3>
        <p class="muted">每受理一个口径就留一张回执；样本被替换或缺失时回执会显示原样本不可取得，不会给出改善结论。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>回执</th>
              <th>口径</th>
              <th>图谱版本</th>
              <th>受理时快照</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="receipt in receipts" :key="receipt.receipt_id" :data-testid="`receipt-${receipt.receipt_id}`">
              <td class="mono">{{ receipt.receipt_id }}</td>
              <td>{{ receipt.scope_label }}</td>
              <td>{{ receipt.graph_version }}</td>
              <td>{{ receipt.snapshot.numerator }}/{{ receipt.snapshot.denominator }} · {{ formatRate(receipt.snapshot.error_rate_pct) }}</td>
              <td>{{ receipt.status }}</td>
              <td>
                <button class="link" type="button" :data-testid="`verify-${receipt.receipt_id}`" @click="verify(receipt.receipt_id)">
                  核对
                </button>
              </td>
            </tr>
            <tr v-if="!receipts.length">
              <td colspan="6" class="empty-state">尚未同步受理范围</td>
            </tr>
          </tbody>
        </table>
        <div v-if="verification" class="verify-box" data-testid="verify-result">
          <strong>{{ verification.receipt_id }} · {{ verification.status }}</strong>
          <p v-if="verification.available">
            重算 {{ verification.recomputed?.numerator }}/{{ verification.recomputed?.denominator }} ·
            {{ formatRate(verification.recomputed?.error_rate_pct) }}；
            漂移 分子 {{ verification.drift?.numerator }}、分母 {{ verification.drift?.denominator }}、可派发 {{ verification.drift?.dispatchable }}
          </p>
          <p v-else>
            {{ verification.reason }}
            <template v-if="verification.missing_sample_ids?.length">
              （缺失：{{ verification.missing_sample_ids.join('、') }}）
            </template>
            ；受理时快照 {{ verification.snapshot.numerator }}/{{ verification.snapshot.denominator }} 保留，不给改善结论。
          </p>
        </div>
      </section>

      <!-- 保留治理看板原有的指标台账（登记、筛选、流转），指标页与其共用同一模块 key -->
      <section class="panel ledger-panel" data-testid="govern-ledger">
        <h3>治理指标台账</h3>
        <p class="muted">可复核指标由审计取样计算，台账记录仍按原有流程登记与流转。</p>
        <WorkbenchView module-key="govern_dash" />
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import WorkbenchView from '@/views/WorkbenchView.vue'
import {
  loadGovernDashboard,
  loadRemediation,
  syncRemediation,
  verifyReceipt,
} from '@/api/quality-service'
import {
  formatDelta,
  formatRate,
  type DashboardPayload,
  type ReceiptVerification,
  type RemediationPlan,
  type ScopeKey,
} from '@/domain/govern_dash'

const router = useRouter()
const dashboard = ref<DashboardPayload | null>(null)
const remediation = ref<RemediationPlan | null>(null)
const verification = ref<ReceiptVerification | null>(null)
const scope = ref<ScopeKey>('expanded')
const loading = ref(false)
const syncing = ref(false)
const errorMessage = ref('')
const syncMessage = ref('')

const scopeOptions: { scope: ScopeKey; label: string }[] = [
  { scope: 'expanded', label: '新样本口径（全部取样）' },
  { scope: 'overlap', label: '旧范围口径（仅重叠实体）' },
]

const comparison = computed(() => dashboard.value!.comparison)
const receipts = computed(() => dashboard.value?.receipts ?? [])
const scopeLabel = computed(() => (scope.value === 'expanded' ? '新样本口径' : '旧范围口径'))

const currentMetrics = computed(() => {
  if (!dashboard.value) return null as never
  return scope.value === 'expanded' ? dashboard.value.metrics : dashboard.value.legacy_scope_metrics
})

const overlapEntityCount = computed(
  () => currentMetrics.value.strata.find((item) => item.stratum === 'overlap')?.entity_count ?? 0,
)
const newEntityCount = computed(
  () => currentMetrics.value.strata.find((item) => item.stratum === 'new')?.entity_count ?? 0,
)

function stratumLabel(stratum: string): string {
  return { overlap: '重叠样本', new: '新增样本', all: '全量样本' }[stratum] ?? stratum
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    dashboard.value = await loadGovernDashboard()
    remediation.value = await loadRemediation(2, scope.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '指标读取失败'
  } finally {
    loading.value = false
  }
}

async function selectScope(next: ScopeKey) {
  scope.value = next
  verification.value = null
  syncMessage.value = ''
  try {
    remediation.value = await loadRemediation(2, next)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整改清单读取失败'
  }
}

async function sync() {
  syncing.value = true
  syncMessage.value = ''
  errorMessage.value = ''
  try {
    const result = await syncRemediation(2, scope.value)
    syncMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '同步失败'
  } finally {
    syncing.value = false
  }
}

async function verify(receiptId: string) {
  errorMessage.value = ''
  try {
    verification.value = await verifyReceipt(receiptId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回执核对失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.scope-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.scope-tab { border: 1px solid var(--border); background: #fff; border-radius: 999px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
.scope-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.metric-strip { display: flex; gap: 12px; margin-bottom: 12px; }
.metric-strip .stat-card { display: flex; flex-direction: column; gap: 2px; }
.stat-note { font-size: 12px; color: var(--muted); }
.callout { border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; border: 1px solid var(--border); background: #fff; }
.callout.warn { border-color: #f0b429; background: #fffbeb; }
.callout.danger { border-color: #ef4444; background: #fef2f2; }
.callout.ok { border-color: #22c55e; background: #f0fdf4; }
.callout p { margin: 6px 0 0; font-size: 13px; }
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-top: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.panel h3 { margin: 0 0 6px; font-size: 15px; }
.muted { color: var(--muted); font-size: 12px; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.skipped-block { margin-top: 10px; font-size: 12px; }
.skipped-block ul { margin: 6px 0 0; padding-left: 18px; }
.sync-message { color: #166534; font-size: 13px; margin-top: 10px; }
.verify-box { margin-top: 10px; padding: 10px; border: 1px dashed var(--border); border-radius: 6px; font-size: 13px; }
.verify-box p { margin: 4px 0 0; color: var(--muted); }
</style>
