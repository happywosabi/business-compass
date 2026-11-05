<script setup lang="ts">
import { ref, watch } from 'vue'
import type { OrchardParams, OrchardSection, Variety, Grade } from '@/api/orchard'
import { variety, grade, channel, orchardChanges } from '@/api/orchard'
import OrchardNumber from './OrchardNumber.vue'
const props = defineProps<{ parameters: OrchardParams; busy?: boolean; preview?: boolean }>()
const emit = defineEmits<{ submit: [changes: Record<string, unknown>]; dirty: [] }>()
const draft = ref<OrchardSection>(JSON.parse(JSON.stringify(props.parameters.orchard ?? {})))
const year = new Date().getFullYear()
const start = ref(draft.value.period?.base.start ?? `${year}-01-01`)
const end = ref(draft.value.period?.base.end ?? `${year}-12-31`)
const audience = ref(draft.value.audience?.base ?? '')
const varieties = ref<Variety[]>(draft.value.varieties?.base ?? [])
const shared = ref(
  draft.value.shared_costs?.base ?? { land_rent: null, maintenance: null, other: null },
)
const supply = ref(draft.value.supply?.base ?? {})
const localError = ref('')
watch([draft, start, end, audience, varieties, shared, supply], () => emit('dirty'), { deep: true })
const costs = {
  inputs: '农资投入',
  irrigation: '灌溉水电',
  paid_labor: '已付人工（含采收）',
  other: '其他直接成本',
} as const
const supplyFields = {
  specification: '品种等级 / 包装规格',
  supply_dates: '供货起止时间',
  available_quantity: '对外可供数量',
  minimum_order: '起订量',
  shipping_areas: '发货地区 / 配送范围',
  verified_attributes: '已核实特点及依据（如认证、检测）',
} as const
function addVariety() {
  varieties.value.push(variety())
}
function splitGrade(v: Variety) {
  v.grades = [...v.grades!, { ...grade(), name: '', share: 0 }]
}
function toggleRetail(g: Grade) {
  if (g.channels!.length === 1) {
    g.channels!.push(channel(g.channels![0]!.kind === 'wholesale' ? 'retail' : 'wholesale', 0))
  } else {
    g.channels = [{ ...g.channels![0]!, share: 1 }]
  }
}
function ratio(event: Event) {
  return Number((event.target as HTMLInputElement).value) / 100
}
function submit() {
  localError.value = ''
  if (varieties.value.some((v) => !v.name.trim())) {
    localError.value = '请填写每个品种的名称，或删除空白品种。'
    return
  }
  const next: OrchardSection = {
    ...draft.value,
    period: {
      base: { start: start.value, end: end.value },
      source: 'user',
      note: '用户确认的经营期',
    },
    audience: audience.value
      ? { base: audience.value as 'wholesale' | 'retail' | 'mixed', source: 'user' }
      : null,
    varieties: { base: varieties.value, source: 'user' },
    shared_costs: { base: shared.value, source: 'user' },
    supply: {
      base: Object.fromEntries(
        Object.entries(supply.value).map(([k, v]) => [k, v === '' ? null : v]),
      ),
      source: 'user',
    },
  }
  emit('submit', orchardChanges(next))
}
</script>
<template>
  <form class="orchard-form" @submit.prevent="submit">
    <section id="group-basic" class="bc-card orchard-section">
      <header>
        <span class="eyebrow">01 / REPORTING PERIOD</span>
        <h2>先圈定，这一季的账</h2>
        <p class="sub">适用于已投产果园。所有品种共用同一期间，建议覆盖完整生产年。</p>
      </header>
      <div class="orchard-grid">
        <label class="input-label"
          >开始日期<input v-model="start" class="bc-input" type="date" required /></label
        ><label class="input-label"
          >结束日期<input v-model="end" class="bc-input" type="date" :min="start" required
        /></label>
        <label id="group-product" class="input-label"
          >主要卖给谁<select v-model="audience" class="bc-input">
            <option value="">请确认销售对象</option>
            <option value="wholesale">以采购商批发为主</option>
            <option value="retail">以消费者零售为主</option>
            <option value="mixed">批发与零售并重</option>
          </select></label
        >
      </div>
      <p class="sub">主要客户只决定内容创作的默认对象。实际销售比例请在每个品种中填写。</p>
    </section>
    <section id="group-shop" class="orchard-section">
      <header class="orchard-heading">
        <div>
          <span class="eyebrow">02 / FRUIT & SALES</span>
          <h2>每个品种，都有自己的收成</h2>
        </div>
        <button type="button" class="text-link" @click="addVariety">＋ 添加品种 / 采收批次</button>
      </header>
      <p v-if="!varieties.length" class="bc-card sub">
        从一个品种开始。产量、售价、成本不确定时可以先留空，稍后再补。
      </p>
      <TransitionGroup name="fruit" tag="div" class="variety-list">
        <article v-for="(v, i) in varieties" :key="v.id" class="bc-card variety-card">
          <header class="orchard-heading">
            <span class="eyebrow">FRUIT {{ String(i + 1).padStart(2, '0') }}</span
            ><button type="button" class="text-link" @click="varieties.splice(i, 1)">
              移除品种
            </button>
          </header>
          <div class="orchard-grid">
            <label class="input-label"
              >水果 / 品种 / 批次<input
                v-model="v.name"
                class="bc-input"
                placeholder="例如：红心蜜柚 · 秋收"
                maxlength="80" /></label
            ><label class="input-label"
              >面积（亩，可选）<input
                v-model.number="v.area_mu"
                class="bc-input"
                type="number"
                min="0.01"
                step="any"
                placeholder="用于区分亩产与总产量"
                @change="v.area_mu = v.area_mu || null" /></label
            ><label class="input-label"
              >采收开始（可选）<input
                v-model="v.harvest_start"
                class="bc-input"
                type="date"
                @change="v.harvest_start = v.harvest_start || null" /></label
            ><label class="input-label"
              >采收结束（可选）<input
                v-model="v.harvest_end"
                class="bc-input"
                type="date"
                @change="v.harvest_end = v.harvest_end || null"
            /></label>
            <OrchardNumber
              v-model="v.harvest_kg"
              label="本期总采收量"
              unit="kg"
              range
            /><OrchardNumber v-model="v.loss_rate" label="采后损耗率" rate range />
          </div>
          <p class="sub">
            这里填总采收重量（公斤），1 斤 = 0.5 kg，1 吨 = 1000
            kg。售价也统一为元/kg；箱价先确认水果净重。损耗后可售量，再乘下方售出率。
          </p>
          <details class="grade-details" :open="v.grades!.length > 1">
            <summary>
              等级与销售渠道
              <small>{{
                v.grades!.length === 1 ? '默认统货 · 可展开分级' : `${v.grades!.length} 个等级`
              }}</small>
            </summary>
            <div class="grade-list">
              <div v-for="(g, gi) in v.grades" :key="g.id" class="grade-card">
                <div class="orchard-grid">
                  <label class="input-label"
                    >等级名称<input v-model="g.name" class="bc-input" maxlength="80" /></label
                  ><label class="input-label"
                    >占可售重量（%）<input
                      class="bc-input"
                      type="number"
                      min="0"
                      max="100"
                      step="any"
                      :value="g.share * 100"
                      @input="g.share = ratio($event)" /></label
                  ><OrchardNumber v-model="g.sell_through" label="预计售出率" rate range />
                </div>
                <button
                  v-if="v.grades!.length > 1"
                  class="text-link"
                  type="button"
                  @click="v.grades!.splice(gi, 1)"
                >
                  移除等级
                </button>
                <div v-for="c in g.channels" :key="c.id" class="channel-card">
                  <div class="orchard-grid">
                    <label class="input-label"
                      >渠道<select v-model="c.kind" class="bc-input">
                        <option value="wholesale">批发</option>
                        <option value="retail">零售</option>
                      </select></label
                    ><label class="input-label"
                      >占该等级售出量（%）<input
                        class="bc-input"
                        type="number"
                        min="0"
                        max="100"
                        step="any"
                        :value="c.share * 100"
                        @input="c.share = ratio($event)" /></label
                    ><OrchardNumber
                      v-model="c.price"
                      label="销售单价"
                      unit="元/kg"
                      range
                    /><OrchardNumber
                      v-model="c.packaging_per_kg"
                      label="包装费用"
                      unit="元/kg"
                      range
                    /><OrchardNumber
                      v-model="c.logistics_per_kg"
                      label="物流费用"
                      unit="元/kg"
                      range
                    /><OrchardNumber v-model="c.fee_rate" label="渠道佣金 / 手续费" rate range />
                  </div>
                </div>
                <button type="button" class="text-link" @click="toggleRetail(g)">
                  {{ g.channels!.length === 1 ? '＋ 同时做另一渠道' : '仅保留第一个渠道' }}
                </button>
              </div>
              <button type="button" class="text-link" @click="splitGrade(v)">＋ 添加等级</button>
            </div>
          </details>
          <p class="sub">
            等级占比合计 100%；每个等级的渠道占比也合计
            100%，不能重复计算同一批水果。未售出部分收入为零。
          </p>
          <h3>这个品种的直接支出</h3>
          <div class="orchard-grid">
            <OrchardNumber
              v-for="(label, key) in costs"
              :key="key"
              v-model="v.costs![key]"
              :label="label"
              unit="元/期"
              range
            />
          </div>
        </article>
      </TransitionGroup>
      <button type="button" class="add-fruit" @click="addVariety">＋ 再记一个品种</button>
    </section>
    <section id="group-costs" class="bc-card orchard-section">
      <header>
        <span class="eyebrow">03 / COSTS & FAMILY</span>
        <h2>全园共用，只记一次</h2>
      </header>
      <div class="orchard-grid">
        <OrchardNumber
          v-model="shared.land_rent"
          label="本期土地租金"
          unit="元/期"
          range
        /><OrchardNumber
          v-model="shared.maintenance"
          label="本期全园维护"
          unit="元/期"
          range
        /><OrchardNumber
          v-model="shared.other"
          label="其他共用支出"
          unit="元/期"
          range
        /><OrchardNumber
          v-model="draft.unpaid_labor"
          label="未付酬家庭劳动估值"
          unit="元/期"
          range
        /><OrchardNumber
          v-model="draft.equipment"
          label="设备购置（可选，单列）"
          unit="元/期"
          range
        />
      </div>
      <p class="sub">
        已经支付的人工填在品种直接支出；自己与家人未领工资的劳动在此估值，避免重复扣除。没有发生的支出请明确填
        0，未填会保留为未知。设备不计入经营支出。
      </p>
    </section>
    <section id="group-none" class="bc-card orchard-section">
      <header>
        <span class="eyebrow">04 / OPEN FOR BUSINESS</span>
        <h2>让好收成，被更多人看见</h2>
        <p class="sub">这些是可用于获客文案的资料。可选填，成本与收益不会传给营销 AI。</p>
      </header>
      <div class="orchard-grid">
        <label v-for="(label, key) in supplyFields" :key="key" class="input-label"
          >{{ label
          }}<input
            v-model="supply[key]"
            class="bc-input"
            :maxlength="key === 'verified_attributes' ? 1000 : 200"
            placeholder="只填已确认的事实" /></label
        ><label class="input-label"
          >每箱水果净重（kg）<input
            v-model.number="supply.pack_net_kg"
            class="bc-input"
            type="number"
            min="0.01"
            step="any"
            placeholder="不含包装"
            @change="supply.pack_net_kg = supply.pack_net_kg || null"
        /></label>
      </div>
    </section>
    <p v-if="localError" class="form-error" role="alert">{{ localError }}</p>
    <div class="orchard-save">
      <span class="sub">保存草稿后可随时补充。核算时会检查所有必填数值。</span
      ><van-button native-type="submit" type="primary" :loading="busy">{{
        preview ? '预览这一版试算 ↗' : '保存果园档案 ✓'
      }}</van-button>
    </div>
  </form>
</template>
<style scoped>
.orchard-form {
  display: grid;
  gap: 24px;
  min-width: 0;
}
.orchard-section {
  display: grid;
  gap: 18px;
  scroll-margin-top: 20px;
}
.orchard-section header h2 {
  margin: 6px 0;
}
.orchard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.orchard-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.variety-list {
  display: grid;
  gap: 20px;
}
.variety-card {
  display: grid;
  gap: 20px;
  border-top: 2px solid var(--accent-line);
  transition:
    border-color 0.25s,
    box-shadow 0.25s;
}
.variety-card:hover {
  border-top-color: var(--accent);
}
h3 {
  font-size: 14px;
  font-weight: 600;
}
.grade-details {
  border: 1px solid var(--line);
  border-radius: 10px;
}
summary {
  cursor: pointer;
  padding: 16px;
  color: var(--accent-ink);
  font-size: 14px;
}
summary small {
  color: var(--muted);
  margin-left: 8px;
}
.grade-list {
  display: grid;
  gap: 18px;
  padding: 0 16px 16px;
}
.grade-card {
  display: grid;
  gap: 14px;
  padding: 16px 0;
  border-top: 1px solid var(--line-soft);
}
.channel-card {
  background: var(--accent-soft);
  padding: 16px;
  border-radius: 8px;
}
.add-fruit {
  border: 1px dashed var(--accent-line);
  border-radius: 10px;
  padding: 18px;
  color: var(--accent-ink);
  background: var(--accent-soft);
  cursor: pointer;
  transition:
    background 0.25s,
    transform 0.25s;
}
.add-fruit:hover {
  transform: translateY(-2px);
}
.orchard-save {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px 0;
}
.fruit-enter-active,
.fruit-leave-active,
.fruit-move {
  transition:
    opacity 0.35s,
    transform 0.35s;
}
.fruit-enter-from,
.fruit-leave-to {
  opacity: 0;
  transform: translateY(14px);
}
@media (max-width: 600px) {
  .orchard-grid {
    grid-template-columns: 1fr;
  }
  .channel-card {
    padding: 12px;
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
