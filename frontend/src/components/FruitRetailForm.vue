<script setup lang="ts">
import { computed, reactive } from 'vue'
import type { components } from '@/api/schema'
import type { Template } from '@/api/profiles'
import type { Amount } from '@/api/orchard'
import OrchardNumber from './OrchardNumber.vue'

type FruitParams = components['schemas']['FruitRetailParams']
const props = defineProps<{
  parameters: FruitParams
  template: Template
  busy: boolean
  trial?: boolean
}>()
const emit = defineEmits<{ submit: [changes: Record<string, unknown>]; dirty: [] }>()
const draft = reactive<Record<string, any>>(
  JSON.parse(JSON.stringify(props.parameters.fruit ?? {})),
)
const publicFacts = reactive<Record<string, string>>(
  Object.fromEntries(
    Object.entries(draft.public_facts?.base ?? {}).filter(
      (entry): entry is [string, string] => typeof entry[1] === 'string',
    ),
  ),
)
const groups = computed(() =>
  Object.entries(props.template.groups ?? {}).map(([key, label]) => ({
    key,
    label,
    fields: props.template.fields.filter((f) => f.stage === key && visible(f.key.split('.')[1]!)),
  })),
)
function visible(key: string) {
  if (key === 'public_facts') return false
  if (['daily_transactions', 'avg_ticket'].includes(key))
    return draft.revenue_basis?.base === 'transactions'
  if (['sales_amount', 'sales_period'].includes(key))
    return draft.revenue_basis?.base !== 'transactions'
  if (['gross_margin', 'loss_rate'].includes(key)) return draft.cost_basis?.base !== 'inclusive'
  if (key === 'procurement_ratio') return draft.cost_basis?.base === 'inclusive'
  return true
}
const options: Record<string, Record<string, string>> = {
  revenue_basis: { revenue: '直接填营业额', transactions: '交易笔数 × 客单价' },
  sales_period: { day: '每天', month: '每月' },
  cost_basis: { margin_loss: '未损耗毛利率 ＋ 损耗率', inclusive: '已含损耗综合采购成本率' },
}
function select(key: string, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  draft[key] = value ? { base: value, source: 'user' } : null
  if (key === 'cost_basis') {
    for (const k of value === 'inclusive' ? ['gross_margin', 'loss_rate'] : ['procurement_ratio'])
      draft[k] = null
  }
  if (key === 'revenue_basis') {
    for (const k of value === 'transactions'
      ? ['sales_amount', 'sales_period']
      : ['daily_transactions', 'avg_ticket'])
      draft[k] = null
  }
  emit('dirty')
}
function submit() {
  const publicValue = Object.fromEntries(Object.entries(publicFacts).filter(([, v]) => v.trim()))
  draft.public_facts = Object.keys(publicValue).length
    ? { base: publicValue, source: 'user' }
    : null
  emit(
    'submit',
    Object.fromEntries(
      props.template.fields.map((f) => [f.key, draft[f.key.split('.')[1]!] ?? null]),
    ),
  )
}
const publicLabels = {
  products: '实际在售水果',
  retail_prices: '零售价及单位（如 元/斤、元/盒）',
  confirmed_origin: '已确认产地',
  delivery_rules: '配送范围与收费规则',
  promotions: '已确认活动与限制',
}
</script>
<template>
  <form class="fruit-form" @submit.prevent="submit" @input="emit('dirty')">
    <section class="bc-card fruit-intro chart-grid">
      <span class="eyebrow">FRUIT RETAIL / 整店账本</span>
      <h2>把新鲜生意，算得更清楚。</h2>
      <p class="sub">
        {{
          parameters.stage === 'operating'
            ? '从现在向前看。历史投入仅作记录，可用现金不知道就留空。'
            : '从开店投入到日常结余，先把关键口径对齐。'
        }}拿不准的先留空，没有支出请明确填 0。
      </p>
      <details>
        <summary>毛利、损耗和库存怎么填？</summary>
        <p>
          未损耗毛利率＝（售价－进价）÷售价；加价率以进价为分母，两者不同。损耗率按采购成本加权。综合采购成本率已含损耗，选它就不会再次扣损耗。
        </p>
        <p>
          采购成本率＝（1－未损耗毛利率）÷（1－损耗率）。例如毛利30%、损耗10%，月销售9万元对应采购成本7万元。
        </p>
        <p>
          月采购付款受库存增减影响，不能直接当销售成本。库存用进货成本填，只计一次资金占用；备货参考资金＝日采购成本×备货天数。
        </p>
      </details>
    </section>
    <section
      v-for="(group, i) in groups"
      :id="`group-${group.key}`"
      :key="group.key"
      class="bc-card fruit-group"
      :style="{ '--order': i }"
    >
      <header>
        <span class="eyebrow">0{{ i + 1 }}</span>
        <h2>{{ group.label }}</h2>
      </header>
      <div class="fruit-fields">
        <div v-for="field in group.fields" :key="field.key" class="fruit-field">
          <label v-if="options[field.key.split('.')[1]!]" class="input-label"
            ><span>{{ field.label }}</span>
            <select
              class="bc-input"
              :aria-label="field.label"
              :value="draft[field.key.split('.')[1]!]?.base ?? ''"
              @change="select(field.key.split('.')[1]!, $event)"
            >
              <option value="">请选择口径</option>
              <option
                v-for="(text, value) in options[field.key.split('.')[1]!]"
                :key="value"
                :value="value"
              >
                {{ text }}
              </option>
            </select>
          </label>
          <label
            v-else-if="['location', 'channels'].includes(field.key.split('.')[1]!)"
            class="input-label"
            ><span>{{ field.label }}</span
            ><input
              class="bc-input"
              :value="draft[field.key.split('.')[1]!]?.base ?? ''"
              maxlength="300"
              @input="
                draft[field.key.split('.')[1]!] = {
                  base: ($event.target as HTMLInputElement).value,
                  source: 'user',
                }
              "
          /></label>
          <OrchardNumber
            v-else
            :model-value="draft[field.key.split('.')[1]!] as Amount"
            :label="
              parameters.stage === 'operating' &&
              ['fruit.renovation', 'fruit.equipment', 'fruit.deposit'].includes(field.key)
                ? `${field.label}（历史，可选）`
                : field.label
            "
            :unit="field.unit ?? undefined"
            :rate="field.unit === '比例'"
            :unbounded-rate="field.key === 'fruit.procurement_ratio'"
            :range="field.three_tier"
            @update:model-value="draft[field.key.split('.')[1]!] = $event"
          />
          <small v-if="field.ask" class="sub field-help">{{ field.ask }}</small>
        </div>
      </div>
    </section>
    <section class="bc-card">
      <h2>对外商品与活动资料</h2>
      <p class="sub">用于内容创作。补上实际商品、价格和规则，让 AI 更懂你的店。</p>
      <label v-for="(label, key) in publicLabels" :key="key" class="input-label"
        ><span>{{ label }}</span
        ><textarea
          v-model="publicFacts[key]"
          class="bc-input"
          rows="2"
          :maxlength="key === 'confirmed_origin' ? 500 : 1000"
        />
      </label>
    </section>
    <div class="fruit-save bc-card">
      <p class="sub">
        {{
          trial ? '先预览变化，确认后再应用到档案。' : '每次保存保留修改记录；之后还能继续补充。'
        }}
      </p>
      <van-button native-type="submit" type="primary" :loading="busy">{{
        trial ? '预览试算 ↗' : '保存水果店档案 ↗'
      }}</van-button>
    </div>
  </form>
</template>
<style scoped>
.fruit-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.fruit-intro {
  background-color: var(--accent-soft);
  border-color: var(--accent-line);
}
.fruit-intro h2 {
  font-size: 25px;
  line-height: 1.5;
}
.fruit-intro details {
  font-size: 13px;
  line-height: 1.9;
  color: var(--muted);
}
summary {
  cursor: pointer;
  color: var(--accent-ink);
}
.fruit-group {
  scroll-margin-top: 20px;
  animation: compass-rise 0.5s calc(var(--order) * 50ms) var(--ease) both;
}
header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
header h2 {
  font-size: 18px;
}
.fruit-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px 18px;
}
.fruit-field {
  min-width: 0;
}
.field-help {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.7;
}
.fruit-save {
  position: sticky;
  bottom: 16px;
  z-index: 2;
  border-color: var(--accent-line);
  box-shadow: 0 8px 30px #132b3812;
}
@media (max-width: 600px) {
  .fruit-fields {
    grid-template-columns: 1fr;
  }
  .fruit-save {
    bottom: 76px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .fruit-group {
    animation: none;
  }
}
</style>
