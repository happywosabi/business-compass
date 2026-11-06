<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { profilesApi, type ProfileSummary as Profile } from '@/api/profiles'
import { contentApi, type Draft, type Topic } from '@/api/content'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import MarkdownText from '@/components/MarkdownText.vue'
import HotTopicPicker from '@/components/HotTopicPicker.vue'
import { fillField, pendingFields, removeFieldLine } from '@/utils/contentDraft'
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const hotPanel = ref<HTMLElement>()
const hotTopicId = ref('')
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
const audience = ref<'buyers' | 'consumers'>('consumers')
const fruitRetail = computed(
  () => profiles.value.find((p) => p.id === id.value)?.industry === 'fruit_retail',
)
const orchard = computed(
  () => profiles.value.find((p) => p.id === id.value)?.template_key === 'orchard',
)
const fieldValues = ref<Record<string, string>>({})
const pending = computed(() => pendingFields(editor.value))
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
  hotTopicId.value = ''
  active.value = undefined
  facts.value = ''
  const params = id.value ? (await profilesApi.get(id.value)).parameters : undefined
  audience.value =
    params && 'orchard' in params && params.orchard?.audience?.base === 'wholesale'
      ? 'buyers'
      : 'consumers'
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
    hotPanel.value?.scrollIntoView({
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
      hot_topic_id: hotTopicId.value || undefined,
      platform: platform.value,
      voice: voice.value,
      audience: orchard.value ? audience.value : undefined,
      confirmed_facts: facts.value,
    })
    active.value = result
    fieldValues.value = {}
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
  fieldValues.value = {}
}
function fill(field: string) {
  editor.value = fillField(editor.value, field, fieldValues.value[field] ?? '')
}
function omit(field: string) {
  editor.value = removeFieldLine(editor.value, field)
}
async function copy() {
  if (pending.value.length) {
    showToast('先填写待填项，或删去不需要的行，再复制')
    return
  }
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
    profiles.value = await profilesApi.summaries()
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
      <h2>先认识你的生意</h2>
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
          <span class="sub">{{
            orchard
              ? '供货合作 · 水果选购 · 果园日常'
              : fruitRetail
                ? '水果选购 · 到货清单 · 门店日常'
                : '日历 · 门店日常 · 已核实来源'
          }}</span>
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
                    : topic.kind === 'orchard'
                      ? '果园经营'
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
        <div ref="hotPanel" class="hot-panel">
          <HotTopicPicker
            v-model="hotTopicId"
            :profile-id="id"
            :verified="auth.isVerified"
            :disabled="busy"
          />
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
          <template v-else>
            <section v-if="pending.length" class="draft-fields">
              <div>
                <span class="eyebrow">还差一点你的真实信息</span>
                <h3>补齐 {{ pending.length }} 处，就能复制</h3>
                <p>AI 把需要你确认的内容留了空位。填入实际情况，或删去不想写的整行。</p>
              </div>
              <div v-for="field in pending" :key="field" class="draft-field">
                <label class="input-label">
                  {{ field.slice(4, -1) }}
                  <input v-model="fieldValues[field]" class="bc-input" placeholder="填写真实情况" />
                </label>
                <div class="draft-field-actions">
                  <button
                    class="text-link"
                    :disabled="!fieldValues[field]?.trim()"
                    @click="fill(field)"
                  >
                    填入文案 ↗
                  </button>
                  <button class="text-link" @click="omit(field)">删去此行</button>
                </div>
              </div>
            </section>
            <MarkdownText :content="editor" />
            <details>
              <summary>发布前，改成你自己的话</summary>
              <textarea
                v-model="editor"
                class="bc-input draft-editor"
                rows="8"
                aria-label="编辑文案"
              />
              <p class="sub">编辑保留在当前页面；待填项处理完后即可复制，请核对产品和活动规则。</p>
            </details>
            <van-button type="primary" @click="copy">
              {{ pending.length ? '处理待填项后复制 ↗' : '复制这份文案 ↗' }}
            </van-button></template
          >
          <div class="draft-sources">
            <h3>这份草稿的依据</h3>
            <article v-for="source in active.sources" :key="source.title">
              <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer"
                >{{ source.title }} ↗</a
              ><b v-else>{{ source.title }}</b>
              <p>{{ source.excerpt }}</p>
              <small>
                {{ source.publisher ? source.publisher + ' · ' : '' }}
                {{
                  source.published_at
                    ? '发布时间 ' + new Date(source.published_at).toLocaleString('zh-CN') + ' · '
                    : ''
                }}
                获取于 {{ new Date(source.retrieved_at).toLocaleString('zh-CN') }}
              </small>
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
      <aside class="writing-panel bc-card">
        <label v-if="orchard" class="input-label"
          >这篇写给谁<select v-model="audience" class="bc-input">
            <option value="buyers">采购商 · 供货与合作</option>
            <option value="consumers">消费者 · 水果与生活</option>
          </select></label
        >
        <span class="eyebrow">02 / 写给谁，怎么说</span>
        <h2>{{ selected ? selected.title : '先挑一个你想说的话题' }}</h2>
        <p class="sub">{{ selected?.angle ?? '左边的卡片是起点，你的真实经历才是主角。' }}</p>
        <p v-if="hotTopicId" class="hot-selected-note">已关联热点，生成时将联网检索背景资料。</p>
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
            :placeholder="
              orchard
                ? '补充真实规格、采收日记、供货规则。档案中的对外供货资料会自动带入，内部成本收益不会用于文案。'
                : fruitRetail
                  ? '补充实际到货水果、零售价及单位、产地、配送与活动规则；公开商品资料会自动带入。'
                  : '比如：今天到店买奶茶送哪吒周边；可补充真实菜单、价格、活动规则或制作细节。'
            "
          />
        </label>
        <p class="sub">
          想不到该补什么也没关系，AI 会把关键缺项留成待填提示。补齐或删去后再复制发布。
        </p>
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
.hot-panel {
  min-width: 0;
  scroll-margin-top: 20px;
}
.hot-selected-note {
  color: var(--accent-ink);
  font-size: 12px;
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
.draft-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--accent-line);
  border-radius: 10px;
  background: var(--accent-soft);
  animation: compass-rise 0.35s var(--ease);
}
.draft-fields h3 {
  margin: 8px 0;
  font-size: 17px;
}
.draft-fields p {
  color: var(--muted);
  font-size: 12px;
}
.draft-field-actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
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
    order: 4;
    scroll-margin-top: 20px;
  }
  .draft-result {
    order: 5;
    width: 100%;
  }
  .draft-archive {
    order: 6;
    width: 100%;
  }
  .topic-main,
  .writing-panel {
    width: 100%;
  }
  .hot-panel {
    order: 3;
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
