<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  evaluationsApi,
  type Evaluation,
  isFruitEvaluation,
  isStoreEvaluation,
} from '@/api/evaluations'
import { errorMessage } from '@/api/client'
import PageHead from '@/components/PageHead.vue'
import { fundingRange, payback } from '@/utils/finance'
const route = useRoute(),
  items = ref<Evaluation[]>([]),
  busy = ref(false),
  error = ref(''),
  more = ref(true)
async function load() {
  busy.value = true
  try {
    const page = await evaluationsApi.list(String(route.params.id), items.value.length)
    items.value.push(...page)
    more.value = page.length === 30
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
<template>
  <div class="page">
    <PageHead
      title="每一次推演，都留下坐标"
      :back="`/profiles/${route.params.id}`"
      back-label="返回档案"
    />
    <p class="sub">每份结果保留当时的数字。之后修改档案，也不会改变它。</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-if="!busy && !items.length" class="bc-card sub">还没有测算结果，先回档案填好关键数字。</p>
    <router-link
      v-for="(item, i) in items"
      :key="item.id"
      class="bc-card history-card"
      :style="{ '--order': i }"
      :to="`/profiles/${item.profile_id}/results/${item.id}`"
      ><header>
        <span class="eyebrow">{{ new Date(item.created_at).toLocaleString('zh-CN') }}</span
        ><span>↗</span>
      </header>
      <h2>{{ item.label || '一次新的可能性' }}</h2>
      <p>{{ item.summary }}</p>
      <div class="history-stats">
        <template v-if="isFruitEvaluation(item)"
          ><span
            >月结余 {{ item.results.scenarios.base!.monthly_net.toLocaleString('zh-CN') }} 元</span
          ><span>{{
            item.results.stage === 'operating' ? '未来经营预测' : '筹备推演'
          }}</span></template
        >
        <template v-else-if="isStoreEvaluation(item)"
          ><span>准备 {{ fundingRange(item.results.scenarios.base.suggested_funding) }}</span
          ><span>回本 {{ payback(item.results.scenarios.base.payback_month) }}</span></template
        ><template v-else
          ><span
            >经营结余
            {{ item.results.scenarios.base!.operating_surplus.toLocaleString('zh-CN') }} 元</span
          ><span>经营期总账</span></template
        ><small>修订 {{ item.profile_revision }}</small>
      </div></router-link
    ><van-button v-if="more" :loading="busy" @click="load">{{
      items.length ? '再看更早的结果' : '正在读取'
    }}</van-button>
  </div>
</template>
<style scoped>
.history-card {
  text-decoration: none;
  transition:
    transform 0.25s,
    border-color 0.25s;
  animation: compass-rise 0.5s var(--ease) both;
  animation-delay: calc(min(var(--order), 5) * 0.05s);
}
.history-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
}
.history-card header,
.history-stats {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  flex-wrap: wrap;
}
.history-card p {
  font-size: 13px;
  color: var(--muted);
}
.history-stats {
  justify-content: flex-start;
  font-size: 12px;
  border-top: 1px solid var(--line-soft);
  padding-top: 12px;
}
.history-stats small {
  margin-left: auto;
  color: var(--faint);
}
</style>
