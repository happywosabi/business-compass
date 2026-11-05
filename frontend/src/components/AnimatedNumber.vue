<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{ value: number; format?: (value: number) => string; duration?: number }>(),
  { duration: 650 },
)
const shown = ref(props.value)
let frame = 0
watch(
  () => props.value,
  (next, previous) => {
    cancelAnimationFrame(frame)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      shown.value = next
      return
    }
    const start = performance.now()
    function animate(now: number) {
      const fraction = Math.min((now - start) / props.duration, 1)
      shown.value = previous + (next - previous) * (1 - (1 - fraction) ** 3)
      if (fraction < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
  },
)
onScopeDispose(() => cancelAnimationFrame(frame))
</script>

<template>
  <span class="num">{{ format ? format(shown) : Math.round(shown) }}</span>
</template>
