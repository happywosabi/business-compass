<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { OrchardEvaluation } from '@/api/evaluations'
import type { Profile } from '@/api/profiles'
import type { OrchardWhatIf } from '@/api/orchard'
import { evaluationsApi } from '@/api/evaluations'
import { profilesApi } from '@/api/profiles'
import { api, errorMessage } from '@/api/client'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import OrchardForm from '@/components/OrchardForm.vue'
import ReportPanel from '@/components/ReportPanel.vue'
const props = defineProps<{ snapshot: OrchardEvaluation; profile: Profile }>()
const router = useRouter()
const scenario = ref<'base' | 'pessimistic' | 'optimistic'>('base')
const currentProfile = ref(props.profile)
const current = computed(() => props.snapshot.results.scenarios[scenario.value]!)
const period = computed(() => props.snapshot.parameters.orchard?.period?.base)
const cards = [
  ['revenue', '本期销售收入'],
  ['operating_expense', '本期经营支出'],
  ['operating_surplus', '经营结余'],
  ['labor_adjusted_earnings', '扣家庭劳动估值后'],
] as const
const preview = ref<OrchardWhatIf>(),
  changes = ref<Record<string, unknown>>(),
  editing = ref(false),
  busy = ref(false),
  error = ref(''),
  label = ref(props.snapshot.label ?? ''),
  labelOpen = ref(false),
  details = ref(false)
let formVersion = 0
function toggleEditor() {
  clearPreview()
  editing.value = !editing.value
}
function clearPreview() {
  formVersion++
  preview.value = undefined
  changes.value = undefined
}
async function trial(next: Record<string, unknown>) {
  busy.value = true
  error.value = ''
  preview.value = undefined
  changes.value = undefined
  const version = formVersion
  const frozen = JSON.parse(JSON.stringify(next))
  try {
    const result = await api.post<OrchardWhatIf>(`/api/profiles/${props.profile.id}/what-if`, {
      evaluation_id: props.snapshot.id,
      revision: currentProfile.value.revision,
      changes: frozen,
    })
    if (version !== formVersion) return
    preview.value = result
    changes.value = frozen
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function apply() {
  if (!changes.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await evaluationsApi.apply(props.profile.id, {
      evaluation_id: props.snapshot.id,
      revision: currentProfile.value.revision,
      changes: changes.value,
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
    preview.value = undefined
    changes.value = undefined
    error.value = ''
  } catch (e) {
    error.value = errorMessage(e)
  }
}
async function saveLabel() {
  busy.value = true
  try {
    await evaluationsApi.label(props.profile.id, props.snapshot.id, label.value)
    labelOpen.value = false
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function sensitiveLabel(key: string) {
  const parts = key.split('.')
  const variety = props.snapshot.parameters.orchard?.varieties?.base[Number(parts[3])]
  const field = parts.at(-1)!
  const labels: Record<string, string> = {
    harvest_kg: '采收量',
    loss_rate: '采后损耗',
    sell_through: '售出率',
    price: '售价',
    inputs: '农资',
    irrigation: '灌溉',
    paid_labor: '已付人工',
    other: '其他支出',
    land_rent: '土地租金',
    maintenance: '全园维护',
    unpaid_labor: '家庭劳动估值',
    equipment: '设备购置',
    packaging_per_kg: '包装',
    logistics_per_kg: '物流',
    fee_rate: '渠道费率',
  }
  return `${key.includes('varieties') ? (variety?.name ?? '品种') : '全园'} · ${labels[field] ?? field}`
}
</script>
<template>
  <div class="page orchard-result">
    <PageHead
      :title="`${profile.name} · 收成与账本`"
      :back="`/profiles/${profile.id}`"
      back-label="返回档案"
      ><template #actions
        ><router-link class="text-link" :to="`/profiles/${profile.id}/results`"
          >历史测算 ↗</router-link
        ></template
      ></PageHead
    >
    <section class="orchard-banner chart-grid">
      <div>
        <span class="eyebrow">ORCHARD / SEASON REPORT</span>
        <h2>一季辛劳，留下多少收获？</h2>
        <p>{{ period?.start }} — {{ period?.end }} · {{ profile.city }}</p>
        <small class="sub"
          >第 {{ snapshot.profile_revision }} 版档案 · 不可变快照 ·
          {{ new Date(snapshot.created_at).toLocaleDateString('zh-CN') }}</small
        >
      </div>
      <CompassMark :size="95" motion="settle" />
    </section>
    <div class="report-toolbar">
      <button class="text-link" @click="labelOpen = !labelOpen">
        {{ label || '给这份账本命名' }} ✎
      </button>
      <div class="scenario-tabs" role="group" aria-label="选择情景">
        <button
          v-for="(text, key) in { pessimistic: '悲观', base: '中性', optimistic: '乐观' }"
          :key="key"
          :class="{ selected: scenario === key }"
          :aria-pressed="scenario === key"
          @click="scenario = key"
        >
          {{ text }}
        </button>
      </div>
    </div>
    <form v-if="labelOpen" class="bc-card label-form" @submit.prevent="saveLabel">
      <input
        v-model="label"
        class="bc-input"
        maxlength="80"
        aria-label="账本名称"
        placeholder="例如：秋收后核账"
      /><van-button type="primary" native-type="submit" :loading="busy">保存名称</van-button>
    </form>
    <div class="orchard-metrics">
      <article
        v-for="([key, text], i) in cards"
        :key="key"
        class="bc-card metric"
        :style="{ '--order': i }"
      >
        <span>{{ text }}</span
        ><b :class="{ negative: current[key] < 0 }"
          ><AnimatedNumber
            :value="current[key]"
            :format="(v) => Math.round(v).toLocaleString('zh-CN')"
          /><small>元</small></b
        >
        <p class="sub">
          {{
            key === 'labor_adjusted_earnings'
              ? `另扣未付酬家庭劳动 ${current.unpaid_labor.toLocaleString('zh-CN')} 元`
              : key === 'operating_expense'
                ? '直接成本 + 全园共用支出'
                : key === 'operating_surplus'
                  ? '假定销售款全部收齐'
                  : '实际预计售出量 × 对应渠道价格'
          }}
        </p>
      </article>
    </div>
    <p class="accounting-note">
      本期总账假定销售款已全部收齐。设备购置
      {{
        current.equipment_purchases == null
          ? '尚未确认'
          : `${current.equipment_purchases.toLocaleString('zh-CN')} 元（单列）`
      }}；不含折旧、历史建园投入与多年回本测算。
    </p>
    <div class="result-columns">
      <section class="bc-card varieties-result">
        <header>
          <span class="eyebrow">FRUIT BY FRUIT</span>
          <h2>从每个品种，看清贡献</h2>
        </header>
        <div v-for="v in current.varieties" :key="v.id" class="variety-result">
          <div class="row-head">
            <h3>{{ v.name }}</h3>
            <b :class="{ negative: v.contribution < 0 }"
              >贡献 {{ v.contribution.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} 元</b
            >
          </div>
          <div class="yield-track">
            <i :style="{ width: `${v.harvest_kg ? (v.sold_kg / v.harvest_kg) * 100 : 0}%` }" />
          </div>
          <dl>
            <div>
              <dt>采收 / 可售 / 售出</dt>
              <dd>
                {{ v.harvest_kg.toLocaleString() }} / {{ v.saleable_kg.toLocaleString() }} /
                {{ v.sold_kg.toLocaleString() }} kg
              </dd>
            </div>
            <div>
              <dt>未售出可售果</dt>
              <dd>{{ v.unsold_kg.toLocaleString() }} kg</dd>
            </div>
            <div>
              <dt>收入 / 直接支出</dt>
              <dd>{{ v.revenue.toLocaleString() }} / {{ v.direct_cost.toLocaleString() }} 元</dd>
            </div>
          </dl>
        </div>
        <div class="shared-line">
          <span>全园共用支出（仅扣一次）</span><b>{{ current.shared_cost.toLocaleString() }} 元</b>
        </div>
        <p class="sub">
          品种贡献已扣直接支出、包装物流及渠道费，未分摊全园共用支出和未付酬家庭劳动。
        </p>
      </section>
      <aside class="result-aside">
        <section class="bc-card break-even">
          <span class="eyebrow">BREAK EVEN / 收支平衡</span>
          <h2>保本平均售价</h2>
          <b class="num"
            >{{
              current.break_even_price === null
                ? '暂无有限值'
                : current.break_even_price.toFixed(2)
            }}<small v-if="current.break_even_price !== null">元/kg</small></b
          >
          <p class="sub">{{ current.break_even_note }}</p>
        </section>
        <section class="bc-card">
          <h2>哪些变化，更牵动收益</h2>
          <p v-if="!snapshot.results.sensitivity.length" class="sub">
            尚未设置三档范围。请补充产量、售价、售出率或成本范围，再比较风险。
          </p>
          <div
            v-for="(s, i) in snapshot.results.sensitivity.slice(0, 5)"
            :key="i"
            class="sensitivity-row"
          >
            <span
              >{{ sensitiveLabel(String(s.key)) }} ·
              {{ s.scenario === 'pessimistic' ? '悲观' : '乐观' }}</span
            ><b
              >{{ Number(s.delta) >= 0 ? '+' : ''
              }}{{ Number(s.delta).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} 元</b
            >
          </div>
          <p class="sub">每次仅改变一个变量，观察经营结余变化；三档情景保持等级与渠道占比不变。</p>
        </section>
      </aside>
    </div>
    <ReportPanel :key="snapshot.id" :profile-id="profile.id" :evaluation-id="snapshot.id" />
    <section class="bc-card what-if-orchard">
      <header class="row-head">
        <div>
          <span class="eyebrow">WHAT IF / 换个想法试试</span>
          <h2>先试算，再决定</h2>
        </div>
        <button class="text-link" @click="toggleEditor">
          {{ editing ? '收起试算 −' : '展开完整试算 +' }}
        </button>
      </header>
      <p class="sub">
        以这份历史快照为基准。预览保留原账本；确认应用会恢复这版完整参数并建立新快照。
      </p>
      <OrchardForm
        v-if="editing"
        :parameters="snapshot.parameters"
        :busy="busy"
        preview
        @submit="trial"
        @dirty="clearPreview"
      />
      <p v-if="error" class="form-error" role="alert">
        {{ error }} <button class="text-link" @click="refresh">刷新档案修订后重试</button>
      </p>
      <div v-if="preview" class="trial-results" role="status">
        <div>
          <span class="sub">试算经营结余</span
          ><b class="num"
            >{{ preview.modified.scenarios.base!.operating_surplus.toLocaleString() }} 元</b
          >
          <p>
            比原方案 {{ preview.surplus_delta >= 0 ? '增加' : '减少' }}
            {{ Math.abs(preview.surplus_delta).toLocaleString() }} 元
          </p>
          <small
            >扣家庭劳动估值后
            {{
              preview.modified.scenarios.base!.labor_adjusted_earnings.toLocaleString()
            }}
            元</small
          >
        </div>
        <van-button type="primary" :loading="busy" @click="apply"
          >应用完整方案，生成新账本 ↗</van-button
        >
      </div>
    </section>
    <section class="bc-card">
      <button class="text-link" :aria-expanded="details" @click="details = !details">
        {{ details ? '收起' : '查看' }}计算边界与原始参数 {{ details ? '−' : '+' }}</button
      ><template v-if="details"
        ><p v-for="a in snapshot.results.assumptions" :key="a" class="sub">{{ a }}</p>
        <pre>{{ JSON.stringify(snapshot.parameters, null, 2) }}</pre>
      </template>
    </section>
    <router-link class="text-link" :to="`/content?profile=${profile.id}`"
      >账算清了，写一篇供货 / 水果文案 ↗</router-link
    >
  </div>
</template>
<style scoped>
.orchard-result {
  display: grid;
  gap: 22px;
}
.orchard-result > .bc-card {
  margin: 0;
}
.orchard-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 28px;
  border: 1px solid var(--accent-line);
  border-radius: var(--radius-card);
  background-color: var(--accent-soft);
}
.orchard-banner h2 {
  font-size: 26px;
  margin: 10px 0;
}
.orchard-banner p {
  color: var(--muted);
  font-size: 14px;
  margin: 8px 0;
}
.report-toolbar,
.row-head,
.shared-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.scenario-tabs {
  display: flex;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 4px;
}
.scenario-tabs button {
  padding: 8px 18px;
  color: var(--muted);
  background: none;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
  transition: 0.2s;
}
.scenario-tabs .selected {
  color: var(--accent-ink);
  background: var(--accent-soft);
}
.orchard-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.metric {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: compass-rise 0.5s calc(var(--order) * 0.07s) both;
}
.metric > span {
  color: var(--muted);
  font-size: 13px;
}
.metric > b {
  font-family: var(--font-num);
  font-size: clamp(25px, 2.7vw, 38px);
  font-weight: 600;
  white-space: nowrap;
}
.metric small,
.break-even small {
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 400;
  margin-left: 5px;
  color: var(--muted);
}
.negative {
  color: var(--danger, #b45d52);
}
.accounting-note {
  background: var(--accent-soft);
  border-left: 2px solid var(--accent);
  padding: 12px 16px;
  color: var(--muted);
  font-size: 12px;
}
.result-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.varieties-result {
  display: grid;
  gap: 20px;
  margin: 0;
}
.variety-result {
  padding-top: 18px;
  border-top: 1px solid var(--line-soft);
}
h3 {
  font-size: 16px;
}
.row-head > b,
.shared-line {
  font-size: 13px;
}
.yield-track {
  height: 5px;
  background: var(--line-soft);
  margin: 16px 0;
  border-radius: 5px;
  overflow: hidden;
}
.yield-track i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.6s var(--ease);
}
dl {
  display: grid;
  gap: 8px;
  margin: 0;
}
dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}
dt {
  color: var(--muted);
}
dd {
  margin: 0;
  text-align: right;
}
.shared-line {
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.result-aside {
  display: grid;
  gap: 20px;
}
.result-aside > section {
  margin: 0;
  display: grid;
  gap: 14px;
}
.break-even > b {
  font-size: 30px;
  font-weight: 500;
  color: var(--accent-ink);
}
.sensitivity-row {
  display: grid;
  gap: 5px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line-soft);
  font-size: 12px;
}
.sensitivity-row span {
  color: var(--muted);
}
.what-if-orchard {
  display: grid;
  gap: 20px;
}
.trial-results {
  padding: 20px;
  background: var(--accent-soft);
  border: 1px solid var(--accent-line);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
}
.trial-results b {
  display: block;
  font-size: 30px;
  margin: 8px 0;
}
.trial-results p,
.trial-results small {
  font-size: 12px;
}
.label-form {
  display: flex;
  gap: 12px;
}
pre {
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
  padding: 15px;
  background: var(--accent-soft);
}
@media (max-width: 1100px) {
  .orchard-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .result-columns {
    grid-template-columns: 1fr;
  }
  .result-aside {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .orchard-banner {
    padding: 20px;
  }
  .orchard-banner svg {
    width: 55px;
    height: 55px;
    flex-shrink: 0;
  }
  .orchard-banner h2 {
    font-size: 21px;
  }
  .orchard-metrics {
    gap: 10px;
  }
  .metric {
    padding: 16px;
    gap: 10px;
  }
  .metric > b {
    font-size: 27px;
  }
  .metric > span {
    font-size: 12px;
  }
  .result-aside {
    grid-template-columns: 1fr;
  }
  dl div {
    flex-wrap: wrap;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before {
    transition: none !important;
    animation: none !important;
  }
}
</style>
