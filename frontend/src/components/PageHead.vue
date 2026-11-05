<script setup lang="ts">
/** 页面标题。传入 back 时，标题上方显示返回链接（手机上点它返回，桌面上相当于面包屑） */
import type { RouteLocationRaw } from 'vue-router'

import AppIcon from './AppIcon.vue'

defineProps<{ title: string; back?: RouteLocationRaw; backLabel?: string }>()
</script>

<template>
  <header class="page-head">
    <div class="ph-main">
      <RouterLink v-if="back" :to="back" class="ph-back">
        <AppIcon name="chevron-left" :size="16" />{{ backLabel ?? '返回' }}
      </RouterLink>
      <h1>{{ title }}</h1>
    </div>
    <div v-if="$slots.actions" class="ph-actions"><slot name="actions" /></div>
  </header>
</template>

<style scoped>
.ph-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.ph-back {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  align-self: flex-start;
  margin-left: -4px;
  padding: 4px 6px 4px 2px;
  border-radius: 6px;
  font-size: 14px;
  color: var(--muted);
  text-decoration: none;
}
.ph-back:hover {
  color: var(--ink);
  background: var(--surface-2);
}
.ph-actions {
  display: flex;
  gap: 8px;
}
</style>
