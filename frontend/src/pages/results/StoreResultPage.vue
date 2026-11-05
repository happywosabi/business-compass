<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { evaluationsApi, type Evaluation, type StoreEvaluation, type WhatIf } from '@/api/evaluations'
import { profilesApi, type Profile, type Template } from '@/api/profiles'
import { errorMessage } from '@/api/client'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import CashChart from '@/components/CashChart.vue'
import ReportPanel from '@/components/ReportPanel.vue'
import WhatIfPanel from '@/components/WhatIfPanel.vue'
import SourceTag from '@/components/SourceTag.vue'
import { money, wan, payback, monthLabel, fundingRange } from '@/utils/finance'
import { atLeast, unitFor } from '@/utils/format'
import { displayValue } from '@/utils/parameters'
const route = useRoute(),
  router = useRouter()
const snapshot = ref<StoreEvaluation>(),
  profile = ref<Profile>(),
  template = ref<Template>()
const loading = ref(true),
  error = ref(''),
  preview = ref<WhatIf>(),
  details = ref(false),
  sources = ref(false)
const scenario = ref<'base' | 'pessimistic' | 'optimistic'>('base'),
  label = ref(''),
  labelOpen = ref(false),
  saving = ref(false)
const base = computed(() => snapshot.value!.results.scenarios.base)
const current = computed(() => snapshot.value!.results.scenarios[scenario.value])
const requiredOrders = computed(
  () => snapshot.value?.results.thresholds['revenue.daily_orders']?.value,
)
const parameters = computed(() =>
  Object.entries(snapshot.value?.parameters ?? {})
    .filter(([section]) =>
      ['startup', 'revenue', 'variable_cost', 'fixed_cost', 'store'].includes(section),
    )
    .flatMap(([section, entries]) =>
      Object.entries(entries ?? {})
        .filter(([, v]) => v)
        .map(([name, v]) => ({
          key: `${section}.${name}`,
          value: v as { base: unknown; source: string; note?: string | null },
        })),
    ),
)
const titleFor = (key: string) => template.value?.fields.find((f) => f.key === key)?.label ?? key
async function load() {
  loading.value = true
  error.value = ''
  preview.value = undefined
  try {
    const id = String(route.params.id)
    const [p, e, t] = await Promise.all([
      profilesApi.get(id),
      evaluationsApi.get(id, String(route.params.eid)),
      profilesApi.templates(),
    ])
    profile.value = p
    if (e.template_key !== 'physical_store') throw new Error('档案类型不匹配')
    snapshot.value = e
    label.value = e.label ?? ''
    template.value = t.find((x) => x.key === e.template_key)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
async function saveLabel() {
  saving.value = true
  try {
    const updated = await evaluationsApi.label(profile.value!.id, snapshot.value!.id, label.value)
    if (updated.template_key === 'physical_store') snapshot.value = updated
    labelOpen.value = false
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}
async function refresh() {
  try {
    profile.value = await profilesApi.get(String(route.params.id))
  } catch (e) {
    error.value = errorMessage(e)
  }
}
function applied(value: Evaluation) {
  router.push(`/profiles/${value.profile_id}/results/${value.id}`)
}
watch(() => route.params.eid, load)
onMounted(load)
</script>
<template>
  <div class="page result-page">
    <PageHead
      title="给这个想法，一个清晰的坐标"
      :back="`/profiles/${route.params.id}`"
      back-label="返回档案"
      ><template #actions
        ><router-link class="text-link" :to="`/profiles/${route.params.id}/results`"
          >历史测算 ↗</router-link
        ></template
      ></PageHead
    >
    <p v-if="error" class="form-error" role="alert">
      {{ error }} <button class="text-link" @click="load">重试</button>
    </p>
    <div v-if="loading" class="skeleton" style="height: 360px" />
    <template v-else-if="snapshot && profile">
      <section class="result-hero">
        <div>
          <span class="eyebrow">YOUR BUSINESS COORDINATES / 测算结果</span>
          <h2>
            {{ profile.name
            }}<small
              >{{ snapshot.label || '未命名方案' }}
              <button class="text-link" @click="labelOpen = !labelOpen">✎</button></small
            >
          </h2>
          <p>{{ snapshot.summary }}</p>
          <span class="hero-meta"
            >{{ new Date(snapshot.created_at).toLocaleString('zh-CN') }} · 档案修订
            {{ snapshot.profile_revision }} · 引擎 {{ snapshot.engine_version }}</span
          >
        </div>
        <CompassMark :size="110" motion="settle" />
      </section>
      <form v-if="labelOpen" class="label-form" @submit.prevent="saveLabel">
        <input
          v-model="label"
          class="bc-input"
          maxlength="80"
          aria-label="方案标签"
          placeholder="比如：签约前 / 调整房租后"
        /><van-button native-type="submit" type="primary" :loading="saving">保存标签</van-button>
      </form>
      <div class="metric-grid">
        <article class="metric-card featured">
          <span class="metric-index">01 / 准备多少</span>
          <h3>建议准备资金</h3>
          <div class="metric-value">{{ fundingRange(base.suggested_funding) }}</div>
          <p>覆盖前 36 个月现金低点，另留 2–3 个月固定开销。</p>
        </article>
        <article class="metric-card">
          <span class="metric-index">02 / 多久收回</span>
          <h3>收回不可收回投入</h3>
          <div class="metric-value">
            <template v-if="base.payback_month !== null"
              ><AnimatedNumber :value="base.payback_month" /><small>个月</small></template
            ><template v-else>10 年内未回本</template>
          </div>
          <p>
            {{
              base.lease_check === 'pass'
                ? '按中性预估，在租约内收回投入。'
                : '超过租约或无法回本，请先调整方案。'
            }}
          </p>
        </article>
        <article class="metric-card">
          <span class="metric-index">03 / 扛过低谷</span>
          <h3>前 36 个月现金最低点</h3>
          <div class="metric-value">
            {{ base.cash_low ? `${wan(base.cash_low.amount)} 万` : '持续亏损' }}
          </div>
          <p>
            {{
              base.cash_low
                ? `${monthLabel(base.cash_low.month)}；已计入老板工资。`
                : '稳定期仍亏钱，资金建议暂不适用。'
            }}
          </p>
        </article>
        <article class="metric-card">
          <span class="metric-index">04 / 每天底线</span>
          <h3>至少每天卖多少单</h3>
          <div class="metric-value">
            {{ requiredOrders == null ? '无法保本' : money(atLeast(requiredOrders))
            }}<small v-if="requiredOrders != null">{{ unitFor(profile.industry) }}</small>
          </div>
          <p>中性情景下，算上老板工资的保本线。</p>
        </article>
      </div>
      <div class="result-workspace">
        <div class="result-main">
          <section class="bc-card curve-card">
            <header class="bc-card-title">
              <div>
                <span class="eyebrow">36 MONTHS / 资金航线</span>
                <h2>钱会怎样走过这三年</h2>
              </div>
              <span class="chart-badge"
                ><i class="live-dot" />{{
                  preview ? '正在预览另一种可能' : '三种情景，同一张图'
                }}</span
              >
            </header>
            <CashChart :results="snapshot.results" :preview="preview?.after" />
            <p class="sub">
              虚线参考值为 −{{
                money(base.startup.recoverable)
              }}
              元：押金和备货可收回，回本只需覆盖不可收回投入。{{
                base.payback_month && base.payback_month > 36
                  ? `实际回本在第 ${base.payback_month} 个月，超出图表范围。`
                  : ''
              }}
            </p>
          </section>
          <section class="bc-card">
            <div class="bc-card-title">
              <h2>稳定之后，每月会怎样</h2>
              <span class="eyebrow">中性预估</span>
            </div>
            <div class="cash-breakdown">
              <div>
                <span>营业收入</span
                ><b class="num">{{ money(base.steady_monthly_revenue) }}<small>元</small></b>
              </div>
              <div>
                <span>固定开销（含老板工资）</span
                ><b class="num">{{ money(base.steady_fixed_cost) }}<small>元</small></b>
              </div>
              <div>
                <span>扣除全部成本后</span
                ><b class="num" :class="base.steady_monthly_cash < 0 ? 'loss' : 'profit'"
                  >{{ money(base.steady_monthly_cash) }}<small>元</small></b
                >
              </div>
            </div>
            <p class="sub">
              如果暂不计老板工资，每月净现金
              {{ money(base.steady_monthly_cash_excl_owner) }} 元。每单毛利
              {{ money(base.unit_margin, 2) }} 元。
            </p>
          </section>
          <section class="bc-card">
            <div class="bc-card-title">
              <h2>最怕哪个数字变了</h2>
              <span class="sub">按三年末现金下行影响排序</span>
            </div>
            <div v-if="snapshot.results.sensitivity.length" class="sensitivity-list">
              <article
                v-for="(item, i) in snapshot.results.sensitivity.slice(0, 3)"
                :key="item.key"
              >
                <span class="sensitivity-rank num">0{{ i + 1 }}</span>
                <div>
                  <b>{{ titleFor(item.key) }}</b>
                  <p class="sub">悲观时，三年末现金少 {{ wan(item.downside) }} 万</p>
                  <div class="sensitivity-bar">
                    <i
                      :style="{
                        width: `${Math.max(5, (item.downside / Math.max(snapshot.results.sensitivity[0]!.downside, 1)) * 100)}%`,
                      }"
                    />
                  </div>
                </div>
                <span class="sub">回本 {{ payback(item.payback_month.pessimistic) }}</span>
              </article>
            </div>
            <div v-else class="empty-insight">
              <CompassMark :size="45" />
              <p>补充范围后，可分析最怕的变量。</p>
              <router-link class="text-link" :to="`/profiles/${profile.id}`"
                >给关键参数补上悲观和乐观值 ↗</router-link
              >
            </div>
          </section>
          <section v-if="snapshot.results.checks.length" class="bc-card">
            <h2>决定之前，再核实这几件事</h2>
            <ul class="checks">
              <li v-for="check in snapshot.results.checks" :key="check.rule" :class="check.level">
                <span>{{ check.level === 'warning' ? '!' : '↗' }}</span>
                <p>{{ check.message }}</p>
              </li>
            </ul>
          </section>
          <section class="bc-card">
            <button class="detail-toggle" :aria-expanded="details" @click="details = !details">
              <h2>逐月明细</h2>
              <span>{{ details ? '收起 −' : '展开 +' }}</span></button
            ><template v-if="details"
              ><div class="segmented">
                <button
                  v-for="(name, key) in { pessimistic: '悲观', base: '中性', optimistic: '乐观' }"
                  :key="key"
                  :class="{ active: scenario === key }"
                  @click="scenario = key"
                >
                  {{ name }}
                </button>
              </div>
              <div class="table-scroll">
                <table>
                  <caption>
                    金额单位：元；开业前仅记录初始现金
                  </caption>
                  <thead>
                    <tr>
                      <th>月份</th>
                      <th>日均单量</th>
                      <th>营业收入</th>
                      <th>净现金</th>
                      <th>累计现金</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in current.monthly" :key="m.t">
                      <th>{{ m.t === 0 ? '开业前' : `第 ${m.t} 月` }}</th>
                      <td>{{ m.daily_orders == null ? '—' : money(m.daily_orders, 1) }}</td>
                      <td>{{ m.revenue == null ? '—' : money(m.revenue) }}</td>
                      <td>{{ m.cash_flow == null ? '—' : money(m.cash_flow) }}</td>
                      <td :class="m.cash < 0 ? 'loss' : ''">{{ money(m.cash) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div></template
            >
          </section>
          <section class="bc-card">
            <button class="detail-toggle" :aria-expanded="sources" @click="sources = !sources">
              <h2>这些结果，基于哪些数字</h2>
              <span>{{ sources ? '收起 −' : '展开 +' }}</span>
            </button>
            <p class="sub">
              {{ snapshot.results.default_keys.length }}
              项使用默认值。默认值是暂用假设，建议核实后再决定投入。
            </p>
            <div v-if="sources" class="snapshot-parameters">
              <article v-for="p in parameters" :key="p.key">
                <span>{{ titleFor(p.key) }}</span
                ><b>{{ displayValue(p.value.base) }}</b
                ><SourceTag :source="p.value.source" /><small v-if="p.value.note" class="sub">{{
                  p.value.note
                }}</small>
              </article>
            </div>
          </section>
          <ReportPanel
            :key="snapshot.id"
            :profile-id="profile.id"
            :evaluation-id="snapshot.id"
          />
        </div>
        <aside class="result-aside">
          <WhatIfPanel
            :key="snapshot.id"
            :profile="profile"
            :snapshot="snapshot"
            @preview="preview = $event"
            @applied="applied"
            @refresh="refresh"
          />
          <section class="bc-card result-footnote">
            <span class="eyebrow">每个假设，都可以再靠近现实</span>
            <p class="sub">
              结果来自这份快照中的数字。报价、租约和客流有了新信息，就回档案修改，再留下一份新的结果。
            </p>
            <router-link class="text-link" :to="`/profiles/${profile.id}`"
              >回档案核实数字 ↗</router-link
            >
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>
<style scoped>
.result-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 30px;
  border-radius: 12px;
  background: var(--ink);
  color: var(--side-ink);
  position: relative;
  overflow: hidden;
  animation: compass-rise 0.6s var(--ease);
}
.result-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(var(--side-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--side-grid) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: linear-gradient(90deg, transparent, black);
}
.result-hero > * {
  position: relative;
}
.result-hero .eyebrow {
  color: var(--accent-line);
}
.result-hero h2 {
  font-size: 27px;
  margin: 12px 0;
}
.result-hero h2 small {
  display: block;
  color: var(--side-muted);
  font-size: 12px;
  margin-top: 6px;
  font-weight: 400;
}
.result-hero h2 button {
  color: var(--accent-line);
  margin-left: 5px;
}
.result-hero p {
  font-size: 14px;
  max-width: 620px;
}
.hero-meta {
  display: block;
  margin-top: 15px;
  font-size: 11px;
  color: var(--side-muted);
}
.label-form {
  display: flex;
  gap: 10px;
}
.label-form input {
  flex: 1;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.metric-card {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  animation: compass-rise 0.6s var(--ease) both;
  transition:
    transform 0.25s,
    box-shadow 0.25s;
}
.metric-card:nth-child(2) {
  animation-delay: 0.08s;
}
.metric-card:nth-child(3) {
  animation-delay: 0.16s;
}
.metric-card:nth-child(4) {
  animation-delay: 0.24s;
}
.metric-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-card);
}
.metric-card.featured {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.metric-index {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.metric-card h3 {
  font-size: 12px;
  font-weight: 500;
  margin: 10px 0;
}
.metric-value {
  font-family: var(--font-num);
  font-size: clamp(25px, 2.5vw, 36px);
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.25;
}
.metric-value small {
  font-family: var(--font-cn);
  font-size: 12px;
  font-weight: 400;
  margin-left: 5px;
}
.metric-card p {
  font-size: 11px;
  color: var(--muted);
  margin-top: 10px;
}
.result-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  align-items: start;
  gap: 20px;
}
.result-main,
.result-aside {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.result-aside {
  position: sticky;
  top: 25px;
}
.curve-card h2 {
  margin-top: 6px;
}
.chart-badge {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 10px;
  color: var(--muted);
  white-space: nowrap;
}
.cash-breakdown {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.cash-breakdown > div {
  padding: 15px 0;
  border-bottom: 1px solid var(--line-soft);
}
.cash-breakdown span {
  font-size: 11px;
  color: var(--muted);
  display: block;
}
.cash-breakdown b {
  display: block;
  font-size: 27px;
  font-weight: 600;
}
.cash-breakdown small {
  font-family: var(--font-cn);
  font-size: 11px;
  font-weight: 400;
  margin-left: 4px;
}
.profit {
  color: var(--good);
}
.loss {
  color: var(--bad);
}
.sensitivity-list article {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 15px 0;
  border-bottom: 1px solid var(--line-soft);
}
.sensitivity-rank {
  color: var(--accent);
  font-size: 25px;
}
.sensitivity-list article > div {
  flex: 1;
}
.sensitivity-list b {
  font-size: 13px;
}
.sensitivity-bar {
  margin-top: 8px;
  height: 4px;
  background: var(--line-soft);
  border-radius: 4px;
}
.sensitivity-bar i {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width 0.8s;
}
.empty-insight {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  gap: 10px;
  font-size: 13px;
  color: var(--muted);
}
.empty-insight a {
  font-size: 12px;
}
.checks {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.checks li {
  display: flex;
  gap: 10px;
  padding: 12px;
  background: var(--surface-2);
  border-radius: 8px;
  font-size: 13px;
}
.checks li.warning {
  background: var(--warn-soft);
  color: var(--warn);
}
.checks li > span {
  flex: none;
  font-weight: 700;
}
.detail-toggle {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border: 0;
  background: none;
  color: var(--ink);
  text-align: left;
  padding: 0;
  cursor: pointer;
}
.detail-toggle > span {
  font-size: 12px;
  color: var(--muted);
}
.table-scroll {
  overflow-x: auto;
}
.table-scroll table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}
.table-scroll caption {
  text-align: left;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 11px;
}
.table-scroll td,
.table-scroll th {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line-soft);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.table-scroll th:first-child {
  text-align: left;
}
.table-scroll tbody th {
  font-weight: 400;
}
.snapshot-parameters article {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 7px;
  align-items: start;
  padding: 12px 0;
  border-top: 1px solid var(--line-soft);
  font-size: 12px;
}
.snapshot-parameters b {
  font-weight: 500;
  overflow-wrap: anywhere;
}
.snapshot-parameters small {
  grid-column: 1/-1;
  font-size: 11px;
}
.result-footnote a {
  font-size: 13px;
}
@media (max-width: 1199px) {
  .result-workspace {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 14px;
  }
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .chart-badge {
    display: none;
  }
  .cash-breakdown {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .cash-breakdown > div {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
@media (max-width: 767px) {
  .result-workspace {
    display: flex;
    flex-direction: column;
  }
  .result-main,
  .result-aside {
    width: 100%;
  }
  .result-aside {
    position: static;
  }
  .result-hero {
    padding: 22px;
  }
  .result-hero > :last-child {
    display: none;
  }
  .result-hero h2 {
    font-size: 23px;
  }
  .metric-grid {
    gap: 10px;
  }
  .metric-card {
    padding: 14px;
  }
  .metric-value {
    font-size: 27px;
  }
  .metric-card p {
    font-size: 10px;
  }
  .sensitivity-list article > span:last-child {
    display: none;
  }
  .snapshot-parameters article {
    grid-template-columns: 1fr auto;
  }
  .snapshot-parameters b {
    grid-column: 1;
  }
  .snapshot-parameters article > :nth-child(3) {
    grid-column: 2;
    grid-row: 1/3;
  }
}
</style>
