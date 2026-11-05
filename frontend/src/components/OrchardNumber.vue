<script setup lang="ts">
import { ref } from 'vue'
import type { Amount } from '@/api/orchard'
const props = defineProps<{
  modelValue?: Amount | null
  label: string
  unit?: string
  rate?: boolean
  range?: boolean
  unboundedRate?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Amount | null] }>()
const expanded = ref(
  !!(props.modelValue?.pessimistic != null || props.modelValue?.optimistic != null),
)
function update(event: Event, tier: 'base' | 'pessimistic' | 'optimistic') {
  const raw = (event.target as HTMLInputElement).value
  if (tier === 'base' && raw === '') {
    emit('update:modelValue', null)
    return
  }
  if (!props.modelValue && tier !== 'base') return
  emit('update:modelValue', {
    ...props.modelValue,
    base: props.modelValue?.base ?? 0,
    [tier]: raw === '' ? null : Number(raw) / (props.rate ? 100 : 1),
    source: 'user',
    note: tier === 'base' ? null : props.modelValue?.note,
  })
}
</script>
<template>
  <div class="orchard-number">
    <label class="input-label"
      ><span
        >{{ label }} <small>{{ rate ? '%' : unit }}</small></span
      >
      <input
        class="bc-input num"
        type="number"
        min="0"
        :max="rate && !unboundedRate ? 100 : undefined"
        step="any"
        :aria-label="label"
        placeholder="未填写"
        :value="modelValue?.base == null ? '' : modelValue.base * (rate ? 100 : 1)"
        @input="update($event, 'base')"
      />
    </label>
    <button
      v-if="range"
      class="text-link range-toggle"
      type="button"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起范围 −' : '设置三档范围 +' }}
    </button>
    <Transition name="expand"
      ><div v-if="expanded && range" class="range-pair">
        <label
          v-for="[tier, text] in [
            ['pessimistic', '悲观'],
            ['optimistic', '乐观'],
          ] as const"
          :key="tier"
          class="input-label"
          ><small>{{ text }}</small
          ><input
            class="bc-input num"
            type="number"
            min="0"
            :max="rate && !unboundedRate ? 100 : undefined"
            step="any"
            :disabled="!modelValue"
            :aria-label="`${label}${text}`"
            placeholder="同中性"
            :value="modelValue?.[tier] == null ? '' : modelValue[tier]! * (rate ? 100 : 1)"
            @input="update($event, tier)"
        /></label></div
    ></Transition>
    <small v-if="modelValue?.note" class="sub">{{ modelValue.note }}</small>
  </div>
</template>
<style scoped>
.orchard-number {
  min-width: 0;
}
.input-label small {
  color: var(--faint);
  font-weight: 400;
}
.range-toggle {
  font-size: 11px;
  margin-top: 5px;
}
.range-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 8px;
}
</style>
