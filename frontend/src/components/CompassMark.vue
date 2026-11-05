<script setup lang="ts">
/**
 * 罗盘：品牌标志，也用于「正在计算」。
 * - simple：只画外圈和指针（小尺寸的标志用）
 * - motion：settle 指针转一下后定住；seek 指针来回轻摆（等待中）
 * - dark：画在深海蓝底上
 * 动画用 CSS 写，系统开启「减少动态效果」时会被全局规则关掉。
 */
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    size?: number
    simple?: boolean
    dark?: boolean
    motion?: 'none' | 'settle' | 'seek'
  }>(),
  { size: 120, simple: false, dark: false, motion: 'none' },
)

const ticks = computed(() => {
  if (props.simple) return []
  const list: { x1: number; y1: number; x2: number; y2: number; major: boolean }[] = []
  for (let i = 1; i < 36; i++) {
    const angle = (i * 10 * Math.PI) / 180
    const major = i % 9 === 0
    const r1 = major ? 45 : 49
    const r2 = 53
    const round = (n: number) => Math.round(n * 10) / 10
    list.push({
      x1: round(60 + r1 * Math.sin(angle)),
      y1: round(60 - r1 * Math.cos(angle)),
      x2: round(60 + r2 * Math.sin(angle)),
      y2: round(60 - r2 * Math.cos(angle)),
      major,
    })
  }
  return list
})

/** 重播指针动画 */
const playKey = ref(0)
function play() {
  playKey.value++
}
defineExpose({ play })
</script>

<template>
  <svg
    class="compass"
    :class="{ dark, simple }"
    viewBox="0 0 120 120"
    :width="size"
    :height="size"
    aria-hidden="true"
    focusable="false"
  >
    <circle class="ring" cx="60" cy="60" :r="simple ? 54 : 56" />
    <template v-if="!simple">
      <circle class="ring2" cx="60" cy="60" r="43" />
      <line
        v-for="(t, i) in ticks"
        :key="i"
        class="tick"
        :class="{ minor: !t.major }"
        :x1="t.x1"
        :y1="t.y1"
        :x2="t.x2"
        :y2="t.y2"
      />
      <text class="north" x="60" y="17" text-anchor="middle">北</text>
    </template>
    <g :key="playKey" class="needle" :class="motion">
      <path class="n-north" :d="simple ? 'M60 14 L71 60 L49 60 Z' : 'M60 22 L67 60 L53 60 Z'" />
      <path class="n-south" :d="simple ? 'M60 106 L71 60 L49 60 Z' : 'M60 98 L67 60 L53 60 Z'" />
    </g>
    <circle class="pin" cx="60" cy="60" :r="simple ? 7 : 4" />
  </svg>
</template>

<style scoped>
.compass {
  display: block;
  flex: none;
  overflow: visible;
}
.ring {
  fill: var(--surface);
  stroke: var(--ink);
  stroke-width: 2;
}
.simple .ring {
  stroke-width: 7;
}
.ring2 {
  fill: none;
  stroke: var(--line);
  stroke-width: 1;
}
.tick {
  stroke: var(--ink);
  stroke-width: 1.5;
  stroke-linecap: round;
}
.tick.minor {
  stroke: var(--faint);
  stroke-width: 1;
}
.north {
  fill: var(--accent-ink);
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-cn);
}
.n-north {
  fill: var(--accent);
}
.n-south {
  fill: var(--ink);
}
.pin {
  fill: var(--surface);
  stroke: var(--ink);
  stroke-width: 2;
}
.simple .pin {
  stroke-width: 4;
}

/* 深色底 */
.dark .ring {
  fill: transparent;
  stroke: var(--side-ink);
}
.dark .ring2 {
  stroke: rgba(255, 255, 255, 0.16);
}
.dark .tick {
  stroke: var(--side-ink);
}
.dark .tick.minor {
  stroke: var(--side-muted);
}
.dark .north {
  fill: var(--accent);
}
.dark .n-north {
  fill: #c99a52;
}
.dark .n-south {
  fill: var(--side-ink);
}
.dark .pin {
  fill: var(--side);
  stroke: var(--side-ink);
}

/* 指针动画 */
.needle {
  transform-origin: 60px 60px;
  transform-box: view-box;
}
.needle.settle {
  animation: settle 1.15s both;
}
.needle.seek {
  animation: seek 1.6s ease-in-out infinite;
}
@keyframes settle {
  0% {
    transform: rotate(-150deg);
    animation-timing-function: cubic-bezier(0.3, 0.7, 0.4, 1);
  }
  45% {
    transform: rotate(42deg);
    animation-timing-function: ease-in-out;
  }
  64% {
    transform: rotate(-18deg);
    animation-timing-function: ease-in-out;
  }
  80% {
    transform: rotate(8deg);
    animation-timing-function: ease-in-out;
  }
  91% {
    transform: rotate(-3deg);
    animation-timing-function: ease-out;
  }
  100% {
    transform: rotate(0deg);
  }
}
@keyframes seek {
  0%,
  100% {
    transform: rotate(-24deg);
  }
  50% {
    transform: rotate(24deg);
  }
}
</style>
