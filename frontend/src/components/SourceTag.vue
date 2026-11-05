<script setup lang="ts">
import { SOURCES } from '@/utils/parameters'
defineProps<{ source: string }>()
</script>
<template>
  <span class="source-tag" :class="source"
    ><span class="source-dot" />{{ SOURCES[source] ?? source }}</span
  >
</template>
<style scoped>
.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
  color: var(--muted);
  padding: 2px 7px;
  border-radius: 20px;
  background: var(--surface-2);
  white-space: nowrap;
}
.source-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
}
.default {
  color: var(--warn);
  background: var(--warn-soft);
}
.ai_inferred {
  color: var(--accent-ink);
  background: var(--accent-soft);
}
.actual,
.experiment {
  color: var(--good);
  background: var(--good-soft);
}
</style>
