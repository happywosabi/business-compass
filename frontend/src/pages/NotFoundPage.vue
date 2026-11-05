<script setup lang="ts">
import AuthFrame from '@/components/AuthFrame.vue'
import CompassMark from '@/components/CompassMark.vue'
</script>

<template>
  <AuthFrame>
    <section class="bc-card lost">
      <CompassMark :size="88" motion="seek" />
      <h1>这个页面不存在</h1>
      <p class="sub">链接可能写错了，或者页面已经搬走了。</p>
      <van-button type="primary" block to="/">回到首页</van-button>
    </section>
  </AuthFrame>
</template>

<style scoped>
.lost {
  align-items: center;
  text-align: center;
  padding-block: 32px 28px;
}
</style>
