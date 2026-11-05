<script setup lang="ts">
import { computed } from 'vue'
import { emptyValue, LOCATIONS, resolveSchema, type JsonSchema } from '@/utils/parameters'

const props = defineProps<{
  schema: JsonSchema
  definitions: Record<string, unknown>
  modelValue: unknown
  label?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const resolved = computed(() => resolveSchema(props.schema, props.definitions))
const labels: Record<string, string> = {
  role: '岗位',
  count: '人数',
  monthly_cost: '每人月成本（元）',
  name: '渠道名称',
  share: '占比（0–1）',
  fee_rate: '费率（0–1）',
}
const list = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []))
function updateArray(index: number, value: unknown) {
  const next = [...list.value]
  next[index] = value
  emit('update:modelValue', next)
}
function updateObject(key: string, value: unknown) {
  emit('update:modelValue', { ...((props.modelValue as object) ?? {}), [key]: value })
}
function numeric(event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:modelValue', value === '' ? null : Number(value))
}
</script>

<template>
  <div v-if="resolved.type === 'array'" class="array-input">
    <TransitionGroup name="list" tag="div" class="array-rows">
      <div v-for="(item, i) in list" :key="i" class="array-row">
        <span class="array-n num">{{ i + 1 }}</span>
        <SchemaInput
          :schema="resolved.items!"
          :definitions="definitions"
          :model-value="item"
          :label="`${label ?? '数值'} ${i + 1}`"
          @update:model-value="updateArray(i, $event)"
        />
        <button
          class="remove-row"
          type="button"
          :aria-label="`移除第 ${i + 1} 项`"
          @click="
            emit(
              'update:modelValue',
              list.filter((_, index) => index !== i),
            )
          "
        >
          ×
        </button>
      </div>
    </TransitionGroup>
    <button
      type="button"
      class="add-row"
      @click="emit('update:modelValue', [...list, emptyValue(resolved.items!, definitions)])"
    >
      ＋ 添加一项
    </button>
    <p v-if="!list.length" class="sub">没有项目。员工留空表示不请员工。</p>
  </div>
  <div v-else-if="resolved.type === 'object'" class="object-input">
    <label v-for="(child, key) in resolved.properties" :key="key" class="input-label">
      <span>{{ labels[key] ?? key }}</span>
      <SchemaInput
        :schema="child"
        :definitions="definitions"
        :model-value="(modelValue as Record<string, unknown>)?.[key]"
        :label="labels[key] ?? key"
        @update:model-value="updateObject(key, $event)"
      />
    </label>
  </div>
  <select
    v-else-if="resolved.enum"
    class="bc-input"
    :aria-label="label"
    :value="modelValue ?? ''"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <option value="" disabled>请选择</option>
    <option v-for="option in resolved.enum" :key="option" :value="option">
      {{ LOCATIONS[option] ?? option }}
    </option>
  </select>
  <input
    v-else-if="resolved.type === 'number' || resolved.type === 'integer'"
    class="bc-input num"
    type="number"
    inputmode="decimal"
    :aria-label="label"
    :value="modelValue ?? ''"
    :min="resolved.minimum ?? resolved.exclusiveMinimum"
    :max="resolved.maximum"
    :step="resolved.type === 'integer' ? 1 : 'any'"
    required
    @input="numeric"
  />
  <input
    v-else
    class="bc-input"
    type="text"
    :aria-label="label"
    :value="modelValue ?? ''"
    maxlength="100"
    required
    @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  />
</template>

<style scoped>
.array-input,
.array-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.array-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 24px;
  gap: 8px;
  align-items: start;
  padding: 12px 10px;
  background: var(--surface-2);
  border-radius: 8px;
}
.array-n {
  color: var(--accent-ink);
  padding-top: 9px;
}
.object-input {
  display: grid;
  gap: 8px;
}
.remove-row {
  background: none;
  border: 0;
  font-size: 22px;
  color: var(--muted);
  cursor: pointer;
}
.add-row {
  padding: 8px;
  border: 1px dashed var(--line);
  background: transparent;
  color: var(--ink);
  border-radius: 8px;
  cursor: pointer;
}
.input-label {
  font-size: 12px;
}
</style>
