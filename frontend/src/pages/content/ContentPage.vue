<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { profilesApi, type Profile } from '@/api/profiles'
import { contentApi, type Draft, type Topic } from '@/api/content'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import MarkdownText from '@/components/MarkdownText.vue'
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const writingPanel = ref<HTMLElement>()
const profiles = ref<Profile[]>([]),
  id = ref(String(route.query.profile ?? '')),
  topics = ref<Topic[]>([]),
  drafts = ref<Draft[]>([]),
  selected = ref<Topic>(),
  platform = ref('moments'),
  voice = ref('warm'),
  facts = ref(''),
  busy = ref(false),
  loading = ref(true),
  error = ref(''),
  active = ref<Draft>(),
  editor = ref('')
let timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false,
  sequence = 0
async function loadDrafts() {
  const at = sequence,
    currentId = id.value
  const result = await contentApi.drafts(currentId)
  if (at !== sequence || disposed) return
  drafts.value = result
  if (active.value) {
    const next = result.find((d) => d.id === active.value?.id)
    if (next && next.status !== active.value.status) {
      active.value = next
      editor.value = next.content ?? ''
    }
  }
  if (result.some((d) => d.status === 'running'))
    timer = setTimeout(() => loadDrafts().catch((e) => (error.value = errorMessage(e))), 1800)
}
async function load() {
  sequence++
  clearTimeout(timer)
  error.value = ''
  selected.value = undefined
  active.value = undefined
  facts.value = ''
  topics.value = []
  drafts.value = []
  if (!id.value) {
    loading.value = false
    return
  }
  const at = sequence
  loading.value = true
  try {
    const result = await contentApi.topics(id.value)
    if (at !== sequence) return
    topics.value = result
    await loadDrafts()
  } catch (e) {
    if (at === sequence) error.value = errorMessage(e)
  } finally {
    if (at === sequence) loading.value = false
  }
}
function selectTopic(topic: Topic) {
  selected.value = topic
  if (window.innerWidth < 768) {
    writingPanel.value?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
      block: 'start',
    })
  }
}
async function generate() {
  if (!selected.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await contentApi.create(id.value, {
      request_id: crypto.randomUUID(),
      topic_id: selected.value.id,
      platform: platform.value,
      voice: voice.value,
      confirmed_facts: facts.value,
    })
    active.value = result
    editor.value = result.content ?? ''
    await loadDrafts()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function open(draft: Draft) {
  active.value = draft
  editor.value = draft.content ?? ''
}
async function copy() {
  try {
    await navigator.clipboard.writeText(editor.value)
    showToast('已复制，发布前再核对具体事实')
  } catch {
    showToast('请在文本框中选中并复制')
  }
}
watch(id, () => {
  void router.replace({ query: id.value ? { profile: id.value } : {} })
  void load()
})
onMounted(async () => {
  try {
    profiles.value = await profilesApi.list()
    if (!profiles.value.some((p) => p.id === id.value)) {
      id.value = profiles.value[0]?.id ?? ''
      if (!id.value) loading.value = false
    } else await load()
  } catch (e) {
    error.value = errorMessage(e)
    loading.value = false
  }
})
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
})
</script>
<template>
  <div class="page content-page">
    <PageHead title="让附近的人，看见你的认真" />
    <section class="content-hero">
      <div>
        <span class="eyebrow">SMALL STORIES, REAL CONNECTIONS</span>
        <h2>好生意，也值得好好讲述。</h2>
        <p>从真实日常出发，给你的店写一段有温度的话。</p>
      </div>
      <CompassMark :size="95" motion="settle" />
    </section>
    <label v-if="profiles.length" class="profile-select input-label"
      >为哪一家店写<select v-model="id" class="bc-input" :disabled="busy">
        <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
          {{ profile.name }} · {{ profile.city }}
        </option>
      </select></label
    >
    <div v-else-if="!loading" class="bc-card empty-content">
      <CompassMark :size="65" />
      <h2>先认识你的店</h2>
      <p class="sub">建好商业档案，就能找到适合你的内容方向。</p>
      <router-link class="text-link" to="/profiles/new">新建档案 ↗</router-link>
    </div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="skeleton" style="height: 250px" />
    <div v-else-if="id" class="content-workspace">
      <div class="topic-main">
        <header class="bc-card-title topic-heading">
          <div>
            <span class="eyebrow">01 / 选一个切入点</span>
            <h2>今天，聊点什么</h2>
          </div>
          <span class="sub">日历 · 门店日常 · 已核实来源</span>
        </header>
        <div class="topic-grid">
          <button
            v-for="(topic, i) in topics"
            :key="topic.id"
            class="topic-card"
            :class="{ selected: selected?.id === topic.id }"
            :style="{ '--order': i }"
            @click="selectTopic(topic)"
          >
            <header>
              <span class="topic-kind">{{
                topic.kind === 'calendar'
                  ? '营销日历'
                  : topic.kind === 'hot'
                    ? '热点来源'
                    : '门店日常'
              }}</span
              ><span>{{ topic.date || '随时可写' }}</span>
            </header>
            <h3>{{ topic.title }}</h3>
            <p>{{ topic.angle }}</p>
            <span class="topic-arrow">{{
              selected?.id === topic.id ? '已选中 ✓' : '从这里写 ↗'
            }}</span>
          </button>
        </div>
        <section v-if="active" class="bc-card draft-result">
          <header class="bc-card-title">
            <div>
              <span class="eyebrow">03 / 留下你的语气</span>
              <h2>{{ active.topic }}</h2>
            </div>
            <span class="sub">{{ active.platform === 'moments' ? '朋友圈' : '小红书' }}</span>
          </header>
          <div v-if="active.status === 'running'" class="draft-loading">
            <CompassMark :size="55" motion="seek" />
            <p>正在斟酌词句…</p>
            <small>可以离开页面，草稿会保留。</small>
          </div>
          <p v-else-if="active.status === 'failed'" class="form-error">
            生成暂未完成。选择选题后可重新生成，已确认的事实仍在。
          </p>
          <template v-else
            ><MarkdownText :content="active.content ?? ''" />
            <details>
              <summary>发布前，改成你自己的话</summary>
              <textarea
                v-model="editor"
                class="bc-input draft-editor"
                rows="8"
                aria-label="编辑文案"
              />
              <p class="sub">编辑保留在当前页面；复制前请核实【待补充】和具体事实。</p>
            </details>
            <van-button type="primary" @click="copy">复制这份文案 ↗</van-button></template
          >
          <div class="draft-sources">
            <h3>这份草稿的依据</h3>
            <article v-for="source in active.sources" :key="source.title">
              <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer"
                >{{ source.title }} ↗</a
              ><b v-else>{{ source.title }}</b>
              <p>{{ source.excerpt }}</p>
              <small>记录日期 {{ source.retrieved_at }}</small>
            </article>
          </div>
        </section>
        <section class="bc-card draft-archive">
          <header class="bc-card-title">
            <h2>已经写过的片段</h2>
            <span class="sub">最近 50 份</span>
          </header>
          <p v-if="!drafts.length" class="sub">第一份文案，就从今天开始。</p>
          <button
            v-for="draft in drafts"
            :key="draft.id"
            class="draft-history"
            @click="open(draft)"
          >
            <span
              ><b>{{ draft.topic }}</b
              ><small
                >{{ new Date(draft.created_at).toLocaleString('zh-CN') }} ·
                {{ draft.platform === 'moments' ? '朋友圈' : '小红书' }}</small
              ></span
            ><span>{{
              draft.status === 'running'
                ? '生成中…'
                : draft.status === 'failed'
                  ? '生成失败'
                  : '查看 ↗'
            }}</span>
          </button>
        </section>
      </div>
      <aside ref="writingPanel" class="writing-panel bc-card">
        <span class="eyebrow">02 / 写给谁，怎么说</span>
        <h2>{{ selected ? selected.title : '先挑一个你想说的话题' }}</h2>
        <p class="sub">{{ selected?.angle ?? '左边的卡片是起点，你的真实经历才是主角。' }}</p>
        <fieldset>
          <legend>发在哪里</legend>
          <div class="segmented">
            <button :class="{ active: platform === 'moments' }" @click="platform = 'moments'">
              朋友圈</button
            ><button
              :class="{ active: platform === 'xiaohongshu' }"
              @click="platform = 'xiaohongshu'"
            >
              小红书
            </button>
          </div>
        </fieldset>
        <label class="input-label"
          >你的语气<select v-model="voice" class="bc-input">
            <option value="warm">温暖、自然</option>
            <option value="simple">简洁、实在</option>
            <option value="playful">轻松、有趣</option>
          </select></label
        ><label class="input-label"
          >补充你确认过的事实<textarea
            v-model="facts"
            class="bc-input"
            rows="5"
            maxlength="2000"
            placeholder="比如：今天拍了手工煮茶过程；用的是真实店内照片。具体价格、活动以你填写的为准。"
          />
        </label>
        <p class="sub">没有提供的价格、地址和活动会留作【待补充】，发布前再确认。</p>
        <van-button
          type="primary"
          :disabled="!selected || !auth.isVerified"
          :loading="busy"
          @click="generate"
          >写一份草稿 ↗</van-button
        >
        <p v-if="!auth.isVerified" class="sub">验证邮箱后可使用 AI 写作。</p>
        <p class="writing-note">每个来源都能回看，每份文案由你决定何时发布。</p>
      </aside>
    </div>
  </div>
</template>
<style scoped>
.content-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 30px;
  background: var(--ink);
  color: var(--side-ink);
  border-radius: 12px;
  animation: compass-rise 0.6s var(--ease);
}
.content-hero .eyebrow {
  color: var(--accent-line);
}
.content-hero h2 {
  font-size: 28px;
  margin: 12px 0;
}
.content-hero p {
  color: var(--side-muted);
  font-size: 13px;
}
.profile-select {
  max-width: 420px;
}
.content-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 22px;
  align-items: start;
}
.topic-main {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.topic-main > header h2 {
  margin-top: 7px;
}
.topic-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.topic-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: left;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
  transition:
    transform 0.25s,
    border-color 0.25s,
    box-shadow 0.25s;
  animation: compass-rise 0.5s var(--ease) both;
  animation-delay: calc(min(var(--order), 5) * 0.06s);
}
.topic-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
  box-shadow: var(--shadow-card);
}
.topic-card.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.topic-card header {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  color: var(--muted);
}
.topic-kind {
  color: var(--accent-ink);
  border: 1px solid var(--accent-line);
  border-radius: 20px;
  padding: 2px 7px;
}
.topic-card h3 {
  font-size: 18px;
}
.topic-card p {
  font-size: 12px;
  color: var(--muted);
  flex: 1;
}
.topic-arrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-ink);
  margin-top: 6px;
}
.writing-panel {
  position: sticky;
  top: 25px;
  border-color: var(--accent-line);
  background: linear-gradient(160deg, var(--surface), var(--accent-soft));
  gap: 20px;
}
.writing-panel fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  font-size: 13px;
}
.writing-panel legend {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 8px;
}
.writing-note {
  font-size: 11px;
  color: var(--muted);
  text-align: center;
}
.draft-loading {
  padding: 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  font-size: 14px;
}
.draft-loading small {
  font-size: 11px;
  color: var(--muted);
}
.draft-editor {
  margin: 12px 0;
}
.draft-result details {
  font-size: 12px;
  color: var(--muted);
}
.draft-result summary {
  cursor: pointer;
}
.draft-sources {
  border-top: 1px solid var(--line);
  padding-top: 15px;
  font-size: 12px;
  color: var(--muted);
}
.draft-sources h3 {
  font-size: 12px;
  color: var(--ink);
}
.draft-sources article {
  padding: 10px 0;
}
.draft-sources b {
  font-weight: 500;
}
.draft-sources p {
  font-size: 11px;
  margin: 5px 0;
}
.draft-sources small {
  font-size: 10px;
  color: var(--faint);
}
.draft-history {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  background: none;
  border: 0;
  border-bottom: 1px solid var(--line-soft);
  padding: 12px 0;
  cursor: pointer;
  color: var(--ink);
  font-size: 12px;
}
.draft-history b {
  display: block;
  font-weight: 500;
}
.draft-history small {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 5px;
}
.empty-content {
  align-items: center;
  padding: 40px;
}
@media (max-width: 1199px) {
  .content-workspace {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 16px;
  }
  .topic-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 767px) {
  .content-workspace {
    display: flex;
    flex-direction: column;
  }
  .topic-main {
    display: contents;
  }
  .topic-heading {
    order: 1;
  }
  .topic-grid {
    order: 2;
    width: 100%;
  }
  .writing-panel {
    order: 3;
    scroll-margin-top: 20px;
  }
  .draft-result {
    order: 4;
    width: 100%;
  }
  .draft-archive {
    order: 5;
    width: 100%;
  }
  .topic-main,
  .writing-panel {
    width: 100%;
  }
  .writing-panel {
    position: static;
  }
  .content-hero {
    padding: 22px;
  }
  .content-hero > :last-child {
    display: none;
  }
  .content-hero h2 {
    font-size: 24px;
  }
  .topic-card {
    padding: 18px;
  }
  .topic-main > header > span {
    display: none;
  }
}
</style>
