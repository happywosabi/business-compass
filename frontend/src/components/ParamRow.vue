<script setup lang="ts">
import type { Field, Parameter } from '@/api/profiles'
import { displayParameter } from '@/utils/parameters'
import AppIcon from './AppIcon.vue'
import SourceTag from './SourceTag.vue'
defineProps<{ field: Field; value: Parameter | null; saved?: boolean }>()
defineEmits<{ edit: [event: MouseEvent] }>()
</script>
<template>
  <button
    type="button"
    class="param-row"
    :class="{ missing: !value, saved }"
    @click="$emit('edit', $event)"
  >
    <span class="param-info"
      ><span class="param-label"
        >{{ field.label
        }}<span
          v-if="field.quick_required && !value"
          class="required-dot"
          title="快速测算必填" /></span
      ><SourceTag v-if="value" :source="value.source" /><span v-else class="param-prompt">{{
        field.quick_required ? '先填这一项' : '可稍后补充'
      }}</span></span
    >
    <span class="param-value"
      ><span>{{ displayParameter(value, field.unit, field.key) }}</span
      ><AppIcon :name="saved ? 'check' : 'chevron-right'" :size="15"
    /></span>
  </button>
</template>
<style scoped>
.param-row {
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--line-soft);
  padding: 15px 0;
  background: transparent;
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink);
  cursor: pointer;
  transition:
    background 0.2s,
    padding 0.2s;
}
.param-row:last-child {
  border-bottom: 0;
}
.param-row:hover {
  background: var(--surface-2);
  padding-inline: 8px;
}
.param-info {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  flex-direction: column;
  flex: none;
}
.param-label {
  font-size: 14px;
  display: flex;
  gap: 5px;
  align-items: center;
}
.required-dot {
  height: 5px;
  width: 5px;
  border-radius: 50%;
  background: var(--accent);
}
.param-prompt {
  font-size: 11px;
  color: var(--faint);
}
.param-value {
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  text-align: right;
  min-width: 0;
}
.param-value span {
  overflow-wrap: anywhere;
}
.param-value svg {
  flex: none;
  color: var(--faint);
}
.missing .param-value {
  color: var(--faint);
}
.saved {
  animation: saved-glow 1s var(--ease);
}
.saved svg {
  color: var(--good);
}
@keyframes saved-glow {
  0%,
  35% {
    background: var(--accent-soft);
  }
  100% {
    background: transparent;
  }
}
</style>
