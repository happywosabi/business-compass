<script setup lang="ts">
/**
 * 我的档案。档案功能（后端接口 + 卡片列表）是实施顺序的第 2 步，
 * 这一步先放空状态，点「新建档案」提示即将开放。
 */
import { showToast } from 'vant'

import AppIcon from '@/components/AppIcon.vue'
import CompassMark from '@/components/CompassMark.vue'
import PageHead from '@/components/PageHead.vue'
import { INTRO_STEPS } from '@/content/intro'

function createProfile() {
  showToast('档案功能正在开发，下一步就会开放')
}
</script>

<template>
  <div class="page">
    <PageHead title="我的档案" />

    <section class="bc-card empty">
      <CompassMark :size="88" />
      <h2>还没有档案</h2>
      <p class="sub">说说你想开什么店，AI 一步步帮你把账算清楚，大约 10 分钟。</p>
      <van-button type="primary" class="new-btn" @click="createProfile">
        <span class="btn-inner"><AppIcon name="plus" :size="18" />新建档案</span>
      </van-button>
    </section>

    <section aria-labelledby="how-title" class="how">
      <h2 id="how-title" class="how-title">怎么用</h2>
      <ol class="steps">
        <li v-for="(step, i) in INTRO_STEPS" :key="step.title" class="bc-card step">
          <span class="n num">{{ i + 1 }}</span>
          <div class="step-text">
            <b>{{ step.title }}</b>
            <span class="sub">{{ step.text }}</span>
          </div>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.empty {
  align-items: center;
  text-align: center;
  padding-block: 36px 32px;
  gap: 12px;
}
.empty .sub {
  max-width: 30em;
  font-size: 15px;
  text-wrap: pretty;
}
.new-btn {
  margin-top: 6px;
  min-width: 180px;
}
.btn-inner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.how {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.how-title {
  font-size: 15px;
  color: var(--muted);
}
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}
.step {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 14px 16px;
}
.step-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.step .n {
  font-size: 22px;
  font-weight: 600;
  line-height: 1;
  color: var(--accent-ink);
}
@media (min-width: 768px) {
  .steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

/* 打开页面时卡片依次上浮出现 */
.empty,
.step {
  animation: rise 0.4s var(--ease) both;
}
.step:nth-child(1) {
  animation-delay: 0.08s;
}
.step:nth-child(2) {
  animation-delay: 0.14s;
}
.step:nth-child(3) {
  animation-delay: 0.2s;
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
}
</style>
