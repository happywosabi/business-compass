<script setup lang="ts">
/** 不需要登录的独立页面外框：顶部品牌，中间一张卡片（验证邮箱、重置密码、协议、404） */
import CompassMark from './CompassMark.vue'

defineProps<{ wide?: boolean }>()
</script>

<template>
  <div class="frame chart-grid">
    <header class="frame-top">
      <RouterLink to="/" class="brand">
        <CompassMark :size="26" simple />
        <span>商业罗盘</span>
      </RouterLink>
    </header>
    <main class="frame-body" :class="{ wide }">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.frame {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  padding: 0 max(16px, env(safe-area-inset-right, 0px)) 40px max(16px, env(safe-area-inset-left, 0px));
}
.frame-top {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: max(16px, env(safe-area-inset-top, 0px)) 0 16px;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 17px;
  text-decoration: none;
}
.frame-body {
  width: 100%;
  max-width: 440px;
  margin: 4vh auto 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.frame-body.wide {
  max-width: 760px;
  margin-top: 8px;
}
</style>
