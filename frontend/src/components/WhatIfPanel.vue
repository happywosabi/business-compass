<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { showConfirmDialog } from 'vant'
import { evaluationsApi, type Evaluation, type WhatIf } from '@/api/evaluations'
import type { Profile } from '@/api/profiles'
import { errorMessage } from '@/api/client'
import { money, payback } from '@/utils/finance'
const props = defineProps<{ profile: Profile; snapshot: Evaluation }>()
const emit = defineEmits<{
  preview: [value: WhatIf | undefined]
  applied: [value: Evaluation]
  refresh: []
}>()
const fields = [
  { key: 'revenue.daily_orders', label: '日均单量', unit: '单', step: 1 },
  { key: 'revenue.avg_ticket', label: '客单价', unit: '元', step: 0.5 },
  { key: 'fixed_cost.rent', label: '每月房租', unit: '元', step: 100 },
]
const original = (key: string) => {
  const [s, k] = key.split('.')
  return Number(
    (props.snapshot.parameters as unknown as Record<string, Record<string, { base: number }>>)[s!]![
      k!
    ]!.base,
  )
}
const values = ref<Record<string, number>>({})
const changed = computed(() =>
  Object.fromEntries(
    fields
      .filter((f) => values.value[f.key] !== original(f.key))
      .map((f) => [f.key, values.value[f.key]]),
  ),
)
const preview = ref<WhatIf>(),
  pending = ref(false),
  applying = ref(false),
  error = ref('')
let timer: ReturnType<typeof setTimeout>,
  sequence = 0
function reset() {
  values.value = Object.fromEntries(fields.map((f) => [f.key, original(f.key)]))
}
watch(() => props.snapshot.id, reset, { immediate: true })
watch(
  changed,
  () => {
    const id = ++sequence
    clearTimeout(timer)
    preview.value = undefined
    emit('preview', undefined)
    error.value = ''
    if (!Object.keys(changed.value).length) {
      pending.value = false
      return
    }
    pending.value = true
    timer = setTimeout(async () => {
      try {
        const result = await evaluationsApi.preview(props.profile.id, {
          revision: props.profile.revision,
          evaluation_id: props.snapshot.id,
          changes: changed.value,
        })
        if (id === sequence) {
          preview.value = result
          emit('preview', result)
        }
      } catch (e) {
        if (id === sequence) error.value = errorMessage(e)
      } finally {
        if (id === sequence) pending.value = false
      }
    }, 350)
  },
  { deep: true },
)
async function apply() {
  try {
    await showConfirmDialog({
      title: '把这个方案记进档案？',
      message:
        '将以这份历史结果的全部参数为基础，加上当前滑杆改动，替换档案工作稿并生成一份新结果。之后在档案中做过的其他修改也会被替换。旧测算结果会保留。',
      confirmButtonText: '确认应用并重算',
    })
  } catch {
    return
  }
  applying.value = true
  try {
    emit(
      'applied',
      await evaluationsApi.apply(props.profile.id, {
        revision: props.profile.revision,
        evaluation_id: props.snapshot.id,
        changes: changed.value,
      }),
    )
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    applying.value = false
  }
}
onBeforeUnmount(() => {
  clearTimeout(timer)
  sequence++
})
</script>
<template>
  <section class="bc-card what-if">
    <header>
      <span class="eyebrow">WHAT IF / 看看另一种可能</span>
      <h2>拖一拖，会怎样？</h2>
      <p class="sub">基于这份历史结果试算，确认应用后才保存。</p>
    </header>
    <label v-for="f in fields" :key="f.key" class="slider-field"
      ><span
        >{{ f.label
        }}<b class="num"
          >{{ money(values[f.key]!) }} <small>{{ f.unit }}</small></b
        ></span
      ><input
        v-model.number="values[f.key]"
        type="range"
        :aria-label="f.label"
        :min="f.key === 'revenue.avg_ticket' ? 0.5 : f.key === 'revenue.daily_orders' ? 1 : 0"
        :max="Math.max(original(f.key) * 2, f.key === 'fixed_cost.rent' ? 50000 : 100)"
        :step="f.step"
        :disabled="applying"
      /><span class="range-caption"><small>更保守</small><small>更大胆</small></span></label
    >
    <div class="trial-outcome" aria-live="polite">
      <p v-if="pending" class="sub">正在看看这个可能性…</p>
      <template v-else-if="preview"
        ><span class="sub">稳定期每月净现金</span
        ><b class="trial-number num"
          >{{ money(preview.after.steady_monthly_cash) }} <small>元</small></b
        >
        <p
          :class="
            preview.after.steady_monthly_cash >= preview.before.steady_monthly_cash
              ? 'positive'
              : 'negative'
          "
        >
          比原方案
          {{
            preview.after.steady_monthly_cash >= preview.before.steady_monthly_cash ? '多' : '少'
          }}
          {{
            money(Math.abs(preview.after.steady_monthly_cash - preview.before.steady_monthly_cash))
          }}
          元/月
        </p>
        <p class="sub">收回投入：{{ payback(preview.after.payback_month) }}</p></template
      >
      <p v-else class="sub">改一个数字，曲线和结果会跟着变化。</p>
    </div>
    <p v-if="error" class="form-error" role="alert">
      {{ error }}<button class="text-link" @click="emit('refresh')">刷新档案</button>
    </p>
    <van-button type="primary" :disabled="!preview || pending" :loading="applying" @click="apply"
      >把这个方案记下来 ↗</van-button
    ><button class="text-link reset" :disabled="applying" @click="reset">恢复原来的数字</button>
  </section>
</template>
<style scoped>
.what-if {
  border-color: var(--accent-line);
  background: linear-gradient(155deg, var(--surface), var(--accent-soft));
  gap: 22px;
}
.what-if h2 {
  margin: 7px 0;
  font-size: 22px;
}
.slider-field {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}
.slider-field > span {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.slider-field b {
  font-size: 24px;
  font-weight: 600;
}
.slider-field b small {
  font-size: 12px;
  font-family: var(--font-cn);
  font-weight: 400;
}
.slider-field input {
  width: 100%;
  accent-color: var(--accent);
  cursor: ew-resize;
}
.range-caption {
  color: var(--faint);
  font-size: 11px;
}
.trial-outcome {
  min-height: 110px;
  padding: 14px;
  border: 1px solid var(--accent-line);
  border-radius: 8px;
  background: var(--surface);
}
.trial-number {
  display: block;
  font-size: 34px;
  line-height: 1.3;
}
.trial-number small {
  font-size: 13px;
}
.trial-outcome p {
  font-size: 12px;
}
.positive {
  color: var(--good);
}
.negative {
  color: var(--bad);
}
.reset {
  font-size: 12px;
  color: var(--muted);
}
</style>
