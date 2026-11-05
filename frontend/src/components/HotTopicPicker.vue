<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { contentApi, type Topic } from '@/api/content'
import { errorMessage } from '@/api/client'

const props = defineProps<{ profileId: string; verified: boolean; disabled?: boolean }>()
const selected = defineModel<string>({ default: '' })
const topics = ref<Topic[]>([])
const loading = ref(false)
const message = ref('')
const current = computed(() => topics.value.find((topic) => topic.id === selected.value))
let sequence = 0
const stamp = (value?: string) => value
  ? new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  : ''

async function refresh() {
  if (loading.value || !props.verified) return
  const at = sequence
  const profileId = props.profileId
  loading.value = true
  message.value = ''
  try {
    const result = await contentApi.refreshHotTopics(profileId)
    if (at !== sequence) return
    topics.value = result.topics
    message.value = result.error ?? result.message ?? ''
    if (!topics.value.some((topic) => topic.id === selected.value)) selected.value = ''
  } catch (e) {
    if (at === sequence) message.value = errorMessage(e)
  } finally {
    if (at === sequence) loading.value = false
  }
}
watch(() => props.profileId, async (profileId) => {
  const at = ++sequence
  selected.value = ''
  topics.value = []
  message.value = ''
  loading.value = true
  try {
    const result = await contentApi.hotTopics(profileId)
    if (at !== sequence) return
    topics.value = result
  } catch (e) {
    if (at === sequence) message.value = errorMessage(e)
  } finally {
    if (at === sequence) {
      loading.value = false
    }
  }
}, { immediate: true })
</script>

<template>
  <section class="hot-picker bc-card" :class="{ 'has-topic': current }" :aria-busy="loading">
    <header>
      <div>
        <span class="eyebrow">让日常，接上新鲜话题</span>
        <h3>关联一个热点 <span>可选</span></h3>
      </div>
      <button class="hot-refresh text-link" :disabled="loading || disabled || !verified" @click="refresh">
        <span :class="{ spinning: loading }" aria-hidden="true">↻</span>
        {{ loading ? '正在刷新' : '刷新列表' }}
      </button>
    </header>
    <label class="input-label">
      <span class="sr-only">选择关联热点</span>
      <select v-model="selected" class="bc-input" :disabled="disabled || loading">
        <option value="">不关联，专注自己的故事</option>
        <option v-for="topic in topics" :key="topic.id" :value="topic.id">{{ topic.title }}</option>
      </select>
    </label>
    <Transition name="hot-reveal" mode="out-in">
      <article v-if="current" :key="current.id" class="hot-preview">
        <span class="hot-badge">已关联 ✓</span>
        <p>{{ current.sources[0]?.excerpt || current.title }}</p>
        <div class="hot-meta">
          <a v-if="current.sources[0]?.url" :href="current.sources[0].url" target="_blank" rel="noopener noreferrer">
            {{ current.sources[0].publisher || '查看热点来源' }} ↗
          </a>
          <span>{{ current.sources[0]?.published_at ? '发布' : '采集' }} {{ stamp(current.sources[0]?.published_at || current.sources[0]?.retrieved_at) }}</span>
        </div>
        <small>生成时会重新检索这个热点，并结合你选的切入点写作。门店活动和供货承诺仍以你确认为准。</small>
      </article>
      <p v-else class="hot-hint">从近期行业资讯中挑一个灵感。选中后，AI 会将它与你的真实故事自然关联。</p>
    </Transition>
    <p v-if="message" class="hot-message" role="status">{{ message }}</p>
    <p v-else-if="!loading && !topics.length" class="hot-message" role="status">
      {{ verified ? '暂时没有适合当前档案的近期热点，可以稍后查看，也可以直接写日常。' : '现有来源仍可查看，验证邮箱后可刷新列表。' }}
    </p>
    <small class="hot-footnote">后台定时采集 · 刷新列表不消耗 AI 额度 · 展示近 7 天资讯，非热搜排名</small>
  </section>
</template>

<style scoped>
.hot-picker { gap: 15px; border-color: var(--accent-line); transition: background 0.3s, box-shadow 0.3s; }
.hot-picker.has-topic { background: linear-gradient(145deg, var(--surface), var(--accent-soft)); }
header { display: flex; align-items: center; justify-content: space-between; gap: 15px; }
h3 { margin: 7px 0 0; font-size: 19px; }
h3 span { margin-left: 7px; font-size: 11px; font-weight: 400; color: var(--muted); }
.hot-refresh { display: flex; align-items: center; gap: 5px; flex-shrink: 0; font-size: 12px; }
.hot-refresh:disabled { opacity: 0.55; cursor: default; }
.hot-refresh > span { display: inline-block; font-size: 20px; }
.spinning { animation: hot-spin 1.2s linear infinite; }
.hot-preview { display: flex; flex-direction: column; gap: 10px; padding: 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 9px; }
.hot-preview p { font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
.hot-badge { color: var(--accent-ink); font-size: 11px; }
.hot-meta { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 11px; color: var(--muted); }
.hot-preview small, .hot-footnote { color: var(--muted); font-size: 11px; line-height: 1.7; }
.hot-hint, .hot-message { font-size: 12px; color: var(--muted); line-height: 1.8; }
.hot-message { padding: 10px 12px; border-left: 2px solid var(--accent-line); background: var(--accent-soft); }
.hot-footnote { font-size: 10px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.hot-reveal-enter-active, .hot-reveal-leave-active { transition: opacity 0.18s, transform 0.18s; }
.hot-reveal-enter-from, .hot-reveal-leave-to { opacity: 0; transform: translateY(5px); }
@keyframes hot-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .hot-picker, .hot-reveal-enter-active, .hot-reveal-leave-active { transition: none; }
  .spinning { animation: none; }
}
</style>
