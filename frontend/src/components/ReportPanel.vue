<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import MarkdownText from './MarkdownText.vue'
const props = defineProps<{ profileId: string; evaluationId: string }>()
const auth = useAuthStore()
const report = ref<{ status: string; content?: string }>({ status: 'missing' }),
  loading = ref(true),
  busy = ref(false),
  error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false
const path = `/api/profiles/${props.profileId}/evaluations/${props.evaluationId}/report`
async function load() {
  clearTimeout(timer)
  try {
    const result = await api.get<typeof report.value>(path)
    if (disposed) return
    report.value = result
    error.value = ''
    if (report.value.status === 'running') timer = setTimeout(load, 2000)
  } catch (e) {
    if (disposed) return
    error.value = errorMessage(e)
    // 临时网络故障不抹掉生成状态，回来后继续查询已有任务。
    if (report.value.status === 'running') timer = setTimeout(load, 3000)
  } finally {
    if (!disposed) loading.value = false
  }
}
async function generate() {
  if (loading.value || busy.value || report.value.status === 'running') return
  busy.value = true
  error.value = ''
  try {
    await api.post(path, { request_id: crypto.randomUUID() })
    await load()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
})
</script>
<template>
  <section class="bc-card report-panel">
    <header class="bc-card-title">
      <div>
        <span class="eyebrow">COMPASS NOTES / 看懂数字背后</span>
        <h2>再聊聊，这个生意怎么走</h2>
      </div>
      <span class="report-seal">AI 解读</span>
    </header>
    <p v-if="loading" class="sub" role="status">正在读取已保存的解读状态…</p>
    <MarkdownText v-else-if="report.content" :content="report.content" />
    <div v-else-if="report.status === 'running'" class="report-generating">
      <i class="live-dot" />
      <p>正在核对数字、整理建议…<small>可以离开页面，回来后继续查看。</small></p>
    </div>
    <template v-else-if="!error"
      ><p class="sub">
        {{
          report.status === 'failed'
            ? '解读暂未通过生成或数字核对，请先参考上方数字卡片。'
            : '根据这份测算，解释最需要核实的假设和可以先做的小验证。'
        }}
      </p>
      <van-button :disabled="!auth.isVerified" :loading="busy" @click="generate">{{
        report.status === 'failed' ? '重新生成解读' : '生成一份结果解读'
      }}</van-button>
      <p v-if="!auth.isVerified" class="sub">验证邮箱后可生成 AI 解读。</p></template
    >
    <p v-if="error" class="form-error" role="alert">
      {{ error }} <button class="text-link" @click="load">重新读取状态</button>
    </p>
  </section>
</template>
<style scoped>
.report-panel {
  border-color: var(--accent-line);
}
.report-panel h2 {
  margin-top: 6px;
}
.report-seal {
  border: 1px solid var(--accent-line);
  color: var(--accent-ink);
  background: var(--accent-soft);
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.report-generating {
  display: flex;
  gap: 15px;
  align-items: center;
  padding: 20px;
  font-size: 13px;
}
.report-generating .live-dot {
  animation: report-pulse 1.5s infinite;
}
.report-generating small {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
}
@keyframes report-pulse {
  50% {
    box-shadow: 0 0 0 8px var(--accent-soft);
  }
}
</style>
