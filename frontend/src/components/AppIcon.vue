<script setup lang="ts">
import { computed } from 'vue'

import { ICONS, type IconName, type Shape } from './icons'

const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 20 })
const shapes = computed<Shape[]>(() => ICONS[props.name])
</script>

<template>
  <svg
    class="app-icon"
    viewBox="0 0 24 24"
    :width="size"
    :height="size"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-for="(shape, i) in shapes" :key="i">
      <path v-if="'path' in shape" :d="shape.path" />
      <circle
        v-else-if="'circle' in shape"
        :cx="shape.circle[0]"
        :cy="shape.circle[1]"
        :r="shape.circle[2]"
        :fill="shape.fill ? 'currentColor' : 'none'"
      />
      <rect
        v-else
        :x="shape.rect[0]"
        :y="shape.rect[1]"
        :width="shape.rect[2]"
        :height="shape.rect[3]"
        :rx="shape.rect[4]"
      />
    </template>
  </svg>
</template>

<style scoped>
.app-icon {
  flex: none;
  display: inline-block;
  vertical-align: middle;
}
</style>
