<script setup lang="ts">
/** 用户协议、隐私政策。文字在 src/content/legal.ts */
import { computed } from 'vue'

import AuthFrame from '@/components/AuthFrame.vue'
import { DRAFT, PRIVACY, TERMS } from '@/content/legal'

const props = defineProps<{ doc: 'terms' | 'privacy' }>()
const content = computed(() => (props.doc === 'terms' ? TERMS : PRIVACY))
</script>

<template>
  <AuthFrame wide>
    <article class="bc-card legal">
      <p v-if="DRAFT" class="draft" role="note">草稿：正式上线前需要补充运营方信息并审阅。</p>
      <h1>{{ content.title }}</h1>
      <p class="sub">{{ content.updated }}</p>
      <p class="intro">{{ content.intro }}</p>
      <section v-for="section in content.sections" :key="section.heading">
        <h2>{{ section.heading }}</h2>
        <p v-for="(paragraph, i) in section.paragraphs" :key="i">{{ paragraph }}</p>
      </section>
      <nav class="other" aria-label="其他文档">
        <RouterLink v-if="doc === 'terms'" class="text-link" to="/privacy">查看隐私政策</RouterLink>
        <RouterLink v-else class="text-link" to="/terms">查看用户协议</RouterLink>
      </nav>
    </article>
  </AuthFrame>
</template>

<style scoped>
.legal {
  gap: 12px;
  font-size: 16px;
  line-height: 1.8;
}
.legal h1 {
  font-size: 24px;
}
.legal .intro {
  max-width: 68ch;
}
.legal section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 68ch;
}
.legal h2 {
  margin-top: 8px;
  font-size: 17px;
}
.draft {
  align-self: flex-start;
  font-size: 13px;
  line-height: 1.6;
  padding: 4px 10px;
  border-radius: var(--radius-btn);
  background: var(--warn-soft);
  color: var(--warn);
}
.other {
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
  font-size: 15px;
}
</style>
