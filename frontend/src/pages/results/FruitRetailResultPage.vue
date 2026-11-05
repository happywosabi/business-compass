<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Parameter } from '@/api/profiles'
import { useRouter } from 'vue-router'
import type { FruitEvaluation } from '@/api/evaluations'
import type { Profile, Template } from '@/api/profiles'
import type { components } from '@/api/schema'
import { api, errorMessage } from '@/api/client'
import { evaluationsApi } from '@/api/evaluations'
import { profilesApi } from '@/api/profiles'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import FruitRetailForm from '@/components/FruitRetailForm.vue'
import ReportPanel from '@/components/ReportPanel.vue'
import { formatYuan } from '@/utils/format'
const props = defineProps<{ snapshot: FruitEvaluation; profile: Profile }>()
const router = useRouter()
const selected = ref('base')
const base = computed(() => props.snapshot.results.scenarios[selected.value]!)
const operating = props.snapshot.results.stage === 'operating'
const currentProfile = ref(props.profile)
const template = ref<Template>()
const editor = ref(false),
  busy = ref(false),
  error = ref(''),
  changed = ref(false)
const preview = ref<components['schemas']['FruitWhatIf']>()
const nextChanges = ref<Record<string, unknown>>()
const label = ref(props.snapshot.label ?? ''),
  naming = ref(false)
const cards = [
  ['monthly_revenue', '月营业额'],
  ['monthly_procurement', '月采购成本 · 含损耗'],
  ['monthly_net', '月结余 · 扣老板报酬'],
  ['monthly_net_excl_owner', '月结余 · 未扣老板报酬'],
] as const
const quickKeys = computed(() => {
  const f = props.snapshot.parameters.fruit!
  return [
    f.revenue_basis?.base === 'transactions' ? 'daily_transactions' : 'sales_amount',
    f.cost_basis?.base === 'inclusive' ? 'procurement_ratio' : 'gross_margin',
    ...(f.cost_basis?.base === 'margin_loss' ? ['loss_rate'] : []),
    'rent',
  ]
})
const quickValues = ref<Record<string, number>>(
  Object.fromEntries(
    Object.entries(props.snapshot.parameters.fruit ?? {})
      .filter(([, v]) => typeof v?.base === 'number')
      .map(([k, v]) => [k, Number(v!.base)]),
  ),
)
const quickLabels: Record<string, string> = {
  sales_amount: '营业额',
  daily_transactions: '日均交易笔数',
  gross_margin: '未损耗毛利率',
  procurement_ratio: '含损耗采购成本率',
  loss_rate: '采购成本加权损耗率',
  rent: '月租金',
}
const isRate = (key: string) => ['gross_margin', 'procurement_ratio', 'loss_rate'].includes(key)
function quickMax(key: string): number {
  if (key === 'loss_rate') return 0.999
  if (key === 'gross_margin') return 1
  const f = props.snapshot.parameters.fruit as unknown as Record<string, Parameter>
  if (key === 'procurement_ratio') return Math.max(1.5, Number(f[key]?.base ?? 0) * 2)
  return Math.max(Number(f[key]?.base ?? 0) * 2, key === 'rent' ? 10000 : 1000)
}
function quickTrial() {
  trial(
    Object.fromEntries(
      quickKeys.value.map((key) => [
        `fruit.${key}`,
        { base: quickValues.value[key], source: 'user' },
      ]),
    ),
  )
}
function invalidate() {
  changed.value = true
  preview.value = undefined
  nextChanges.value = undefined
}
async function toggle() {
  editor.value = !editor.value
  invalidate()
  if (editor.value && !template.value) {
    try {
      template.value = (await profilesApi.templates('fruit_retail')).find(
        (t) => t.key === 'physical_store',
      )
    } catch (e) {
      error.value = errorMessage(e)
    }
  }
}
async function trial(changes: Record<string, unknown>) {
  busy.value = true
  error.value = ''
  invalidate()
  const frozen = JSON.parse(JSON.stringify(changes))
  changed.value = false
  try {
    const result = await api.post<components['schemas']['FruitWhatIf']>(
      `/api/profiles/${props.profile.id}/what-if`,
      {
        evaluation_id: props.snapshot.id,
        revision: currentProfile.value.revision,
        changes: frozen,
      },
    )
    if (changed.value) return
    preview.value = result
    nextChanges.value = frozen
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function apply() {
  if (!nextChanges.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await evaluationsApi.apply(props.profile.id, {
      evaluation_id: props.snapshot.id,
      revision: currentProfile.value.revision,
      changes: nextChanges.value,
    })
    await router.push(`/profiles/${props.profile.id}/results/${result.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function refresh() {
  try {
    currentProfile.value = await profilesApi.get(props.profile.id)
    invalidate()
    error.value = ''
  } catch (e) {
    error.value = errorMessage(e)
  }
}
async function saveLabel() {
  busy.value = true
  try {
    await evaluationsApi.label(props.profile.id, props.snapshot.id, label.value)
    naming.value = false
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
const sensitivity = computed(
  () => props.snapshot.results.sensitivity as { key: string; scenario: string; delta: number }[],
)
function sensitiveLabel(key: string): string {
  return (
    template.value?.fields.find((f) => f.key === key)?.label ??
    (
      {
        'fruit.sales_amount': '营业额',
        'fruit.gross_margin': '毛利率',
        'fruit.loss_rate': '损耗率',
        'fruit.rent': '租金',
        'fruit.procurement_ratio': '采购成本率',
        'fruit.staff_cost': '人工支出',
        'fruit.owner_salary': '老板报酬',
        'fruit.utilities': '水电',
        'fruit.daily_transactions': '交易笔数',
        'fruit.avg_ticket': '客单价',
      } as Record<string, string>
    )[key] ??
    key
  )
}
const lastCash = computed(() => base.value.monthly.at(-1)?.cash ?? 0)
const minCash = computed(() => Math.min(...base.value.monthly.map((r) => r.cash), 0))
const maxCash = computed(() => Math.max(...base.value.monthly.map((r) => r.cash), 0))
const pointY = (cash: number) =>
  160 - ((cash - minCash.value) / (maxCash.value - minCash.value || 1)) * 140
const points = computed(() =>
  base.value.monthly.map((r) => `${20 + (r.t / 36) * 660},${pointY(r.cash)}`).join(' '),
)
</script>
<template>
  <div class="page fruit-result">
    <PageHead
      :title="`${profile.name} · 水果店经营推演`"
      :back="`/profiles/${profile.id}`"
      back-label="返回档案"
      ><template #actions
        ><router-link class="text-link" :to="`/profiles/${profile.id}/results`"
          >历史测算 ↗</router-link
        ></template
      ></PageHead
    >
    <section class="fruit-banner chart-grid">
      <div>
        <span class="eyebrow">FRUIT RETAIL / YOUR NEXT CHAPTER</span>
        <h2>新鲜的生意，清楚的账。</h2>
        <p>
          {{ operating ? '经营中 · 未来36个月预测' : '筹备 · 启动投入与未来经营' }} · 起点
          {{ snapshot.results.forecast_start }}
        </p>
        <small class="sub">第 {{ snapshot.profile_revision }} 版档案 · 保存当时的数字与阶段</small>
      </div>
      <CompassMark :size="95" motion="settle" hover-sway />
    </section>
    <div class="result-toolbar">
      <button class="text-link" @click="naming = !naming">{{ label || '给这次推演命名' }} ✎</button>
      <div class="segmented" aria-label="选择情景">
        <button
          v-for="(text, key) in { pessimistic: '悲观', base: '中性', optimistic: '乐观' }"
          :key="key"
          :aria-pressed="selected === key"
          :class="{ active: selected === key }"
          @click="selected = key"
        >
          {{ text }}
        </button>
      </div>
    </div>
    <form v-if="naming" class="bc-card naming" @submit.prevent="saveLabel">
      <input v-model="label" class="bc-input" aria-label="测算名称" maxlength="80" /><van-button
        type="primary"
        native-type="submit"
        :loading="busy"
        >保存名称</van-button
      >
    </form>
    <div class="metric-grid">
      <section
        v-for="([key, title], i) in cards"
        :key="key"
        class="bc-card metric"
        :style="{ '--order': i }"
      >
        <span class="sub">{{ title }}</span
        ><strong :class="{ negative: base[key] < 0 }"
          ><AnimatedNumber :value="base[key]" :format="formatYuan" /> <small>元</small></strong
        >
      </section>
    </div>
    <div class="result-columns">
      <section class="bc-card">
        <span class="eyebrow">BREAK EVEN / 收支平衡</span>
        <h2>每天卖到多少，才能持平？</h2>
        <strong class="major">{{
          base.break_even_daily === null
            ? '无有限保本营业额'
            : `${formatYuan(base.break_even_daily)} 元/天`
        }}</strong>
        <p class="sub">
          {{
            base.break_even_monthly === null
              ? '销售贡献不足以覆盖固定成本，先核实采购与费用口径。'
              : `保本月营业额 ${formatYuan(base.break_even_monthly)} 元；已扣老板报酬。`
          }}
        </p>
        <details>
          <summary>查看成本计算口径</summary>
          <p>
            含损耗采购成本率
            {{ (base.procurement_ratio * 100).toFixed(2) }}%；扣包装、渠道及支付税费后的销售贡献率
            {{ (base.contribution_rate * 100).toFixed(2) }}%。月固定成本
            {{ formatYuan(base.fixed_cost) }} 元。
          </p>
          <p>固定成本÷销售贡献率＝保本营业额；销售贡献率不大于零时，无有限保本值。</p>
        </details>
      </section>
      <section class="bc-card">
        <span class="eyebrow">WORKING CAPITAL / 备货资金</span>
        <h2>{{ operating ? '现有库存，还需要补多少？' : '开店之前，要准备多少？' }}</h2>
        <dl>
          <div>
            <dt>参考备货资金</dt>
            <dd>{{ formatYuan(base.reference_stock) }} 元</dd>
          </div>
          <div>
            <dt>库存资金缺口</dt>
            <dd>{{ formatYuan(base.stock_shortfall) }} 元</dd>
          </div>
          <div v-if="!operating">
            <dt>启动投入（含首批库存）</dt>
            <dd>{{ formatYuan(base.startup_investment ?? 0) }} 元</dd>
          </div>
          <div>
            <dt>{{ operating ? '本次新增备货资金' : '启动投入＋备货缺口' }}</dt>
            <dd>{{ formatYuan(base.funding_required) }} 元</dd>
          </div>
          <div>
            <dt>已知现金下即时缺口</dt>
            <dd>
              {{
                base.cash_shortfall === null
                  ? '未提供可用现金'
                  : `${formatYuan(base.cash_shortfall)} 元`
              }}
            </dd>
          </div>
          <div v-if="base.runway_months !== null">
            <dt>按当前亏损可维持</dt>
            <dd>{{ base.runway_months.toFixed(1) }} 个月</dd>
          </div>
        </dl>
        <p class="sub">
          {{
            operating
              ? '历史装修、设备、押金不再扣除；库存超出参考值也不假定可以原价变现。'
              : '筹备回本（扣/未扣老板报酬）：' +
                (base.payback_month === null ? '120个月内未回本' : `第${base.payback_month}个月`) +
                ' / ' +
                (base.payback_month_excl_owner === null
                  ? '120个月内未回本'
                  : `第${base.payback_month_excl_owner}个月`) +
                '。所需资金只含启动与备货；持续亏损还需额外资金。'
          }}
        </p>
      </section>
    </div>
    <section class="bc-card">
      <span class="eyebrow">CASH PROJECTION / 未来36个月</span>
      <h2>{{ snapshot.parameters.fruit?.available_cash ? '可用现金走势' : '累计资金净变动' }}</h2>
      <p class="sub">
        未提供可用现金时，从本次资金支出开始累计，不表示账户余额。第36个月
        {{ formatYuan(lastCash) }} 元。
      </p>
      <svg class="cash-line" viewBox="0 0 700 190" role="img" aria-label="未来36个月资金预测折线">
        <line
          x1="20"
          x2="680"
          :y1="pointY(0)"
          :y2="pointY(0)"
          stroke="var(--line)"
          stroke-dasharray="4 4"
        />
        <polyline :points="points" fill="none" stroke="var(--accent)" stroke-width="3" />
        <circle
          v-for="row in base.monthly.filter((r) => r.t % 12 === 0)"
          :key="row.t"
          :cx="20 + (row.t / 36) * 660"
          :cy="pointY(row.cash)"
          r="4"
          fill="var(--accent)"
        />
        <text x="20" y="185">起点</text>
        <text x="230" y="185">12个月</text>
        <text x="450" y="185">24个月</text>
        <text x="635" y="185">36个月</text>
      </svg>
      <details>
        <summary>逐月明细</summary>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>月份</th>
                <th>营业额/元</th>
                <th>资金变动/元</th>
                <th>累计/元</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in base.monthly" :key="row.t">
                <td>{{ row.t }}</td>
                <td>{{ formatYuan(row.revenue) }}</td>
                <td>{{ formatYuan(row.cash_flow) }}</td>
                <td>{{ formatYuan(row.cash) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </section>
    <section v-if="sensitivity.length" class="bc-card">
      <h2>哪些假设最影响结余？</h2>
      <p class="sub">一次只变一个参数，其余保持中性。以下为月结余变化。</p>
      <div v-for="(row, i) in sensitivity" :key="i" class="sensitivity-row">
        <span
          >{{ sensitiveLabel(row.key) }} ·
          {{ row.scenario === 'pessimistic' ? '悲观' : '乐观' }}</span
        ><b>{{ formatYuan(row.delta, true) }} 元/月</b>
      </div>
    </section>
    <section class="bc-card">
      <h2>换个假设，再看一眼</h2>
      <p class="sub">
        以这份快照为基准，临时改变营业额、毛利、损耗、房租或备货天数；预览后再决定应用。
      </p>
      <div class="quick-sliders">
        <label v-for="key in quickKeys" :key="key" class="quick-slider input-label">
          <span
            >{{ quickLabels[key] }}
            <b>{{
              isRate(key)
                ? `${(quickValues[key]! * 100).toFixed(1)}%`
                : formatYuan(quickValues[key]!)
            }}</b></span
          >
          <input
            v-model.number="quickValues[key]"
            type="range"
            :aria-label="`试算${quickLabels[key]}`"
            min="0"
            :max="quickMax(key)"
            :step="isRate(key) ? 0.001 : 1"
            @input="invalidate"
          />
        </label>
      </div>
      <van-button :loading="busy" @click="quickTrial">预览这些变化 ↗</van-button>
      <button class="text-link" @click="toggle">{{ editor ? '收起试算 −' : '调整数字 +' }}</button>
      <p v-if="error" class="form-error" role="alert">
        {{ error }} <button class="text-link" @click="refresh">刷新当前档案</button>
      </p>
      <FruitRetailForm
        v-if="editor && template"
        :parameters="snapshot.parameters"
        :template="template"
        :busy="busy"
        trial
        @submit="trial"
        @dirty="invalidate"
      />
      <div v-if="preview" class="preview-card">
        <h3>中性情景月结余变化 {{ formatYuan(preview.surplus_delta, true) }} 元</h3>
        <p>
          调整后月结余 {{ formatYuan(preview.modified.scenarios.base!.monthly_net) }} 元；参考备货
          {{ formatYuan(preview.modified.scenarios.base!.reference_stock) }} 元。
        </p>
        <van-button type="primary" :loading="busy" @click="apply">应用并生成新快照 ↗</van-button>
      </div>
    </section>
    <ReportPanel :profile-id="profile.id" :evaluation-id="snapshot.id" />
    <section class="bc-card">
      <h2>这份推演的边界</h2>
      <p v-for="item in snapshot.results.assumptions" :key="item" class="sub">{{ item }}</p>
      <p class="sub">测算依据填写的假设，需结合实际销售和损耗持续核实。</p>
    </section>
  </div>
</template>
<style scoped>
.fruit-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border: 1px solid var(--accent-line);
  border-radius: 12px;
  background-color: var(--accent-soft);
  animation: compass-rise 0.6s var(--ease);
}
.fruit-banner h2 {
  font-size: 30px;
  margin: 8px 0;
}
.fruit-banner p {
  font-size: 14px;
}
.result-toolbar {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 18px;
  align-items: center;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.metric {
  animation: compass-rise 0.5s calc(var(--order) * 70ms) var(--ease) both;
}
.metric strong {
  font-family: var(--font-num);
  font-size: clamp(24px, 3vw, 36px);
  font-weight: 600;
  white-space: nowrap;
}
strong small {
  font-size: 12px;
  color: var(--muted);
}
.negative {
  color: var(--danger, #a33e37);
}
.result-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
h2 {
  font-size: 20px;
}
.major {
  font-family: var(--font-num);
  font-size: 30px;
  color: var(--accent-ink);
}
details {
  font-size: 13px;
  line-height: 1.9;
  color: var(--muted);
}
summary {
  cursor: pointer;
  color: var(--accent-ink);
}
dl {
  margin: 0;
  display: grid;
  gap: 10px;
  font-size: 13px;
}
dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
dd {
  margin: 0;
  font-family: var(--font-num);
}
.cash-line {
  width: 100%;
  height: auto;
}
.cash-line polyline {
  transition: d 0.5s;
}
.cash-line text {
  fill: var(--muted);
  font-size: 12px;
}
.table-wrap {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
  white-space: nowrap;
  font-size: 12px;
}
td,
th {
  text-align: right;
  padding: 10px;
  border-bottom: 1px solid var(--line-soft);
}
.sensitivity-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line-soft);
}
.quick-sliders {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 22px;
}
.quick-slider > span {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.quick-slider b {
  color: var(--accent-ink);
  font-family: var(--font-num);
  font-weight: 500;
}
.quick-slider input {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
  margin-top: 8px;
}
.preview-card {
  padding: 20px;
  background: var(--accent-soft);
  border-radius: 8px;
  display: grid;
  gap: 12px;
}
.naming {
  flex-direction: row;
}
@media (max-width: 1100px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 767px) {
  .fruit-banner {
    padding: 22px;
  }
  .fruit-banner h2 {
    font-size: 25px;
  }
  .fruit-banner > svg {
    display: none;
  }
  .result-columns {
    grid-template-columns: 1fr;
  }
  .metric-grid {
    gap: 12px;
  }
  .metric {
    padding: 16px;
  }
  .metric strong {
    font-size: 27px;
  }
  .metric .sub {
    font-size: 11px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .fruit-banner,
  .metric {
    animation: none;
  }
}
</style>
