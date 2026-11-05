<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  interviewApi,
  sendInterview,
  type ChatHistory,
  type StreamEvent,
  type Run,
} from '@/api/interview'
import { profilesApi, parameterAt, type Profile, type Template } from '@/api/profiles'
import { evaluationsApi } from '@/api/evaluations'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import MarkdownText from '@/components/MarkdownText.vue'
import SourceTag from '@/components/SourceTag.vue'
import { displayValue } from '@/utils/parameters'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore()
const id = String(route.params.id)
const profile = ref<Profile>(),
  template = ref<Template>(),
  history = ref<ChatHistory>({ messages: [], runs: [] })
const sendingContent = ref('')
const retryAvailable = ref(false)
const draft = ref(''),
  pending = ref(false),
  loading = ref(true),
  error = ref(''),
  streamText = ref(''),
  status = ref(''),
  runId = ref(''),
  quick = ref<string[]>([]),
  cardOpen = ref(false),
  composition = ref(false)
const chatLog = ref<HTMLElement>()
const followLatest = ref(true)
const visible = computed(() =>
  history.value.messages.filter((m) => m.role === 'user' || (!m.tool_calls && m.content)),
)
const resultId = computed(
  () => [...history.value.runs].reverse().find((r) => r.output.evaluation_id)?.output.evaluation_id,
)
const total = computed(() => template.value?.quick_required_keys?.length ?? 0)
const progress = computed(() => total.value - (profile.value?.quick_missing.length ?? total.value))
let controller: AbortController | undefined,
  poll: ReturnType<typeof setTimeout> | undefined,
  disposed = false
const storageKey = `bc-interview-pending-${id}`
let navigating = false
function scroll(force = false) {
  nextTick(() => {
    const log = chatLog.value
    if (!log || (!force && !followLatest.value)) return
    log.scrollTo({
      top: log.scrollHeight,
      behavior:
        force && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'smooth'
          : 'instant',
    })
  })
}
function jumpToLatest() {
  followLatest.value = true
  scroll(true)
}
function trackScroll() {
  const log = chatLog.value
  if (log) followLatest.value = log.scrollHeight - log.scrollTop - log.clientHeight < 100
}
async function openResult(evaluationId: string) {
  if (disposed || navigating) return
  navigating = true
  localStorage.removeItem(storageKey)
  await router.push(`/profiles/${id}/results/${evaluationId}`)
}
async function refreshProfile() {
  profile.value = await profilesApi.get(id)
}
async function restoreHistory() {
  await loadHistory()
  await refreshProfile()
}
async function loadHistory() {
  history.value = await interviewApi.history(id)
  const latest = history.value.runs.at(-1)
  quick.value = latest?.output.quick_replies ?? []
  if (latest?.error) error.value = latest.error
  if (latest?.status === 'running') {
    pending.value = true
    runId.value = latest.id
    recover()
  }
}
async function load() {
  try {
    const [, t] = await Promise.all([refreshProfile(), profilesApi.templates()])
    template.value = t.find((x) => x.key === profile.value!.template_key)
    await loadHistory()
    retryAvailable.value = !!localStorage.getItem(storageKey)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
    scroll(true)
  }
}
function recover() {
  clearTimeout(poll)
  poll = setTimeout(async () => {
    if (disposed) return
    try {
      const run = await interviewApi.run(id, runId.value)
      if (run.status === 'running') {
        status.value = '仍在整理，回复完成后会自动显示…'
        recover()
      } else {
        pending.value = false
        streamText.value = ''
        sendingContent.value = ''
        localStorage.removeItem(storageKey)
        await loadHistory()
        await refreshProfile()
        if (run.output.evaluation_id) {
          await openResult(run.output.evaluation_id)
          return
        }
        scroll()
      }
    } catch (e) {
      pending.value = false
      error.value = errorMessage(e)
    }
  }, 1800)
}
function consume({ event, data }: StreamEvent) {
  if (event === 'run') {
    runId.value = String(data.id)
    localStorage.removeItem(storageKey)
  }
  if (event === 'delta') {
    streamText.value += String(data.text)
    status.value = ''
    scroll()
  }
  if (event === 'replace') streamText.value = String(data.text)
  if (event === 'status') status.value = String(data.text)
  if (event === 'profile') {
    if (data.profile) profile.value = data.profile as Profile
    if (data.quick_replies) quick.value = data.quick_replies as string[]
  }
  if (event === 'error') error.value = String(data.message)
  if (event === 'done' && typeof data.evaluation_id === 'string')
    void openResult(data.evaluation_id)
  if (event === 'resume') {
    const run = data as unknown as Run
    runId.value = run.id
    if (run.status === 'running') recover()
  }
}
async function send(content = draft.value, retry = false) {
  if (pending.value || !content.trim() || !profile.value) return
  let body = {
    request_id: crypto.randomUUID(),
    revision: profile.value.revision,
    content: content.trim(),
  }
  if (retry) {
    const saved = localStorage.getItem(storageKey)
    if (saved) body = JSON.parse(saved)
  }
  runId.value = ''
  sendingContent.value = body.content
  retryAvailable.value = false
  localStorage.setItem(storageKey, JSON.stringify(body))
  draft.value = ''
  error.value = ''
  streamText.value = ''
  pending.value = true
  followLatest.value = true
  scroll(true)
  status.value = '罗盘正在整理思路…'
  quick.value = []
  controller = new AbortController()
  try {
    await sendInterview(id, body, controller.signal, consume)
    if (disposed) return
    await loadHistory()
    await refreshProfile()
    const latest = history.value.runs.at(-1)
    if (latest?.output.evaluation_id) {
      await openResult(latest.output.evaluation_id)
      return
    }
    if (latest?.status !== 'running') {
      pending.value = false
      streamText.value = ''
      sendingContent.value = ''
      status.value = ''
    }
  } catch (e) {
    if (!disposed) {
      error.value = e instanceof Error ? e.message : errorMessage(e)
      if (runId.value) recover()
      else {
        pending.value = false
        retryAvailable.value = true
      }
    }
  }
  scroll()
}
async function cancel() {
  if (runId.value) {
    await interviewApi.cancel(id, runId.value)
    controller?.abort()
    status.value = '正在停止…'
    recover()
  }
}
function keydown(event: KeyboardEvent) {
  if (
    event.key === 'Enter' &&
    !event.shiftKey &&
    !event.isComposing &&
    !composition.value &&
    event.keyCode !== 229
  ) {
    event.preventDefault()
    void send()
  }
}
async function evaluate() {
  if (!profile.value || pending.value) return
  pending.value = true
  try {
    const result = await evaluationsApi.create(id, profile.value.revision)
    await router.push(`/profiles/${id}/results/${result.id}`)
  } catch (e) {
    error.value = errorMessage(e)
    pending.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  clearTimeout(poll)
})
</script>
<template>
  <div class="page interview-page">
    <PageHead
      :title="
        profile?.template_key === 'orchard'
          ? '把果园的收成，一点点聊清楚'
          : '把开店的想法，一点点聊清楚'
      "
      :back="`/profiles/${id}`"
      back-label="返回档案"
    >
      <template #actions>
        <router-link class="text-link" :to="`/profiles/${id}`">手动填写 ↗</router-link>
      </template>
    </PageHead>
    <div v-if="loading" class="skeleton" style="height: 400px" />
    <div v-else-if="profile" class="interview-layout">
      <div class="chat-summary">
        <div>
          <b>{{ profile.name }}</b
          ><span>关键数字 {{ progress }} / {{ total }}</span>
        </div>
        <button class="text-link" :disabled="progress !== total || pending" @click="evaluate">
          {{ progress === total ? '查看测算 ↗' : '继续聊清楚' }}
        </button>
      </div>
      <section class="chat-area bc-card">
        <header class="chat-head">
          <div class="assistant-mark">
            <CompassMark :size="40" motion="seek" />
            <div>
              <b>商业罗盘</b>
              <p>陪你把每一笔账，落到实处</p>
            </div>
          </div>
          <span class="chat-online"
            ><i class="live-dot" />{{ pending ? '正在思考' : '随时继续' }}</span
          >
        </header>
        <div
          ref="chatLog"
          class="chat-log"
          role="log"
          aria-label="访谈消息"
          tabindex="0"
          @scroll="trackScroll"
        >
          <div v-if="!visible.length" class="chat-welcome">
            <CompassMark :size="85" motion="settle" /><span class="eyebrow"
              >每一个好生意，都始于一个问题</span
            >
            <h2>
              {{
                profile?.template_key === 'orchard'
                  ? '你好，聊聊你的果园吧。'
                  : '你好，聊聊你的店吧。'
              }}
            </h2>
            <p>数字拿不准也没关系。我们从你已经知道的事情开始，一次聊一点。</p>
            <button
              class="welcome-prompt"
              :disabled="!auth.isVerified || pending"
              @click="send('我们开始吧，请先问我需要了解的问题')"
            >
              {{
                profile?.template_key === 'orchard' ? '开始记这一季的果园账' : '开始聊我的开店想法'
              }}
              ↗
            </button>
          </div>
          <article
            v-for="message in visible"
            :key="message.id"
            class="chat-message"
            :class="message.role"
          >
            <span class="message-label">{{ message.role === 'user' ? '你' : '商业罗盘' }}</span>
            <div class="message-bubble"><MarkdownText :content="message.content" /></div>
          </article>
          <article v-if="sendingContent" class="chat-message user">
            <span class="message-label">你</span>
            <div class="message-bubble"><MarkdownText :content="sendingContent" /></div>
          </article>
          <article v-if="pending" class="chat-message assistant">
            <span class="message-label">商业罗盘</span>
            <div class="message-bubble streaming">
              <MarkdownText v-if="streamText" :content="streamText" />
              <div v-else class="thinking">
                <i /><i /><i /><span>{{ status || '正在整理…' }}</span>
              </div>
            </div>
          </article>
        </div>
        <button
          v-if="!followLatest"
          class="latest-message text-link"
          @click="jumpToLatest"
        >
          回到最新消息 ↓
        </button>
        <div v-if="error" class="form-error" role="alert">
          {{ error
          }}<button
            v-if="!pending"
            class="text-link"
            @click="restoreHistory"
          >
            恢复对话
          </button>
        </div>
        <button
          v-if="retryAvailable && !pending"
          class="text-link"
          @click="send('恢复上次发送', true)"
        >
          恢复上次发送（不会重复记账）
        </button>
        <div v-if="quick.length && !pending" class="quick-replies">
          <button v-for="text in quick" :key="text" @click="send(text)">{{ text }}</button>
        </div>
        <form class="chat-composer" @submit.prevent="send()">
          <textarea
            v-model="draft"
            class="bc-input"
            aria-label="访谈消息"
            placeholder="想到什么，就从这里说起…"
            maxlength="2000"
            rows="2"
            :disabled="!auth.isVerified"
            @keydown="keydown"
            @compositionstart="composition = true"
            @compositionend="composition = false"
          />
          <div class="composer-actions">
            <span>{{ draft.length }} / 2000 · Enter 发送，Shift + Enter 换行</span
            ><button v-if="pending" type="button" class="send-button stop" @click="cancel">
              停止</button
            ><button
              v-else
              type="submit"
              class="send-button"
              :disabled="!draft.trim() || !auth.isVerified"
            >
              发送 ↑
            </button>
          </div>
        </form>
      </section>
      <aside class="chat-profile">
        <section class="bc-card progress-card">
          <span class="eyebrow">YOUR COORDINATES / 同步记录</span>
          <h2>{{ profile.name }}</h2>
          <p class="sub">{{ profile.city }} · {{ template?.label }}</p>
          <div class="chat-progress">
            <span>快速测算准备度</span><b class="num">{{ progress }} / {{ total }}</b>
          </div>
          <div class="progress-track"><i :style="{ width: `${(progress / total) * 100}%` }" /></div>
          <p class="sub">
            {{
              progress === total
                ? '关键数字齐了，可以先看第一版结果。'
                : `再聊清楚 ${total - progress} 个关键数字，就能先算一下。`
            }}
          </p>
          <van-button type="primary" :disabled="progress !== total || pending" @click="evaluate"
            >先算一下 ↗</van-button
          >
          <router-link v-if="resultId" class="text-link" :to="`/profiles/${id}/results/${resultId}`"
            >打开刚才的测算结果 ↗</router-link
          >
          <button
            class="text-link profile-toggle"
            :aria-expanded="cardOpen"
            @click="cardOpen = !cardOpen"
          >
            {{ cardOpen ? '收起已记录数字 −' : '展开已记录数字 +' }}
          </button>
          <div v-if="cardOpen" class="chat-param-list">
            <template v-for="field in template?.fields" :key="field.key"
              ><div v-if="parameterAt(profile, field.key)">
                <span
                  >{{ field.label
                  }}<SourceTag :source="parameterAt(profile, field.key)!.source" /></span
                ><b>{{
                  displayValue(parameterAt(profile, field.key)!.base, field.unit, field.key)
                }}</b>
              </div></template
            >
          </div>
          <router-link class="text-link" :to="`/profiles/${id}`"
            >手动填写，打开完整档案 ↗</router-link
          >
        </section>
        <p class="chat-note">你提供的数字、暂用估算和默认值会分别标明来源。随时核实，随时调整。</p>
      </aside>
    </div>
  </div>
</template>
<style scoped>
.chat-summary {
  display: none;
}
.interview-page {
  height: 100vh;
  height: 100dvh;
  padding-bottom: 28px;
}
.interview-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 22px;
  align-items: start;
  flex: 1;
  min-height: 0;
}
.chat-area {
  padding: 0;
  overflow: hidden;
  height: 100%;
  min-height: 400px;
  max-height: 980px;
  gap: 14px;
}
.chat-area > :not(.chat-log) {
  flex-shrink: 0;
}
.chat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line-soft);
}
.assistant-mark {
  display: flex;
  gap: 12px;
  align-items: center;
}
.assistant-mark b {
  font-size: 15px;
}
.assistant-mark p {
  font-size: 11px;
  color: var(--muted);
}
.chat-online {
  display: flex;
  gap: 9px;
  align-items: center;
  font-size: 11px;
  color: var(--muted);
}
.chat-log {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: var(--accent) var(--surface-2);
}
.chat-log::-webkit-scrollbar {
  width: 7px;
}
.chat-log::-webkit-scrollbar-track {
  background: var(--surface-2);
}
.chat-log::-webkit-scrollbar-thumb {
  background: var(--accent-line);
  border-radius: 7px;
}
.chat-log > * {
  flex-shrink: 0;
}
.latest-message {
  align-self: center;
  font-size: 12px;
}
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 30px 0;
  gap: 18px;
  animation: compass-rise 0.7s var(--ease);
}
.chat-welcome h2 {
  font-size: 24px;
}
.chat-welcome p {
  font-size: 13px;
  color: var(--muted);
  max-width: 320px;
}
.welcome-prompt {
  margin-top: 8px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  border: 1px solid var(--accent-line);
  padding: 12px 20px;
  border-radius: 30px;
  font-size: 13px;
  cursor: pointer;
  transition:
    transform 0.25s,
    box-shadow 0.25s;
}
.welcome-prompt:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-card);
}
.chat-message {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  animation: compass-rise 0.3s var(--ease);
}
.chat-message.user {
  align-items: flex-end;
}
.message-label {
  font-size: 10px;
  color: var(--faint);
  padding: 0 4px;
}
.message-bubble {
  padding: 14px 18px;
  border-radius: 2px 14px 14px 14px;
  background: var(--surface-2);
  max-width: 92%;
}
.user .message-bubble {
  border-radius: 14px 2px 14px 14px;
  background: var(--ink);
  color: var(--side-ink);
}
.streaming {
  border: 1px solid var(--accent-line);
}
.thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--muted);
  min-height: 26px;
}
.thinking i {
  width: 5px;
  height: 5px;
  background: var(--accent);
  border-radius: 50%;
  animation: thinking-pulse 1.1s infinite;
}
.thinking i:nth-child(2) {
  animation-delay: 0.14s;
}
.thinking i:nth-child(3) {
  animation-delay: 0.28s;
}
.thinking span {
  margin-left: 8px;
}
.quick-replies {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 22px;
}
.quick-replies button {
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-radius: 25px;
  padding: 8px 15px;
  cursor: pointer;
  font-size: 12px;
}
.chat-composer {
  margin: 0 20px 20px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow-card);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}
.chat-composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.chat-composer textarea {
  border: 0;
  padding: 0;
  box-shadow: none;
  min-height: 55px;
  background: none;
  resize: none;
}
.composer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.composer-actions > span {
  font-size: 10px;
  color: var(--faint);
}
.send-button {
  border: 0;
  color: var(--surface);
  background: var(--ink);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: transform 0.2s;
}
.send-button:hover {
  transform: translateY(-2px);
}
.send-button:disabled {
  background: var(--line);
  color: var(--muted);
}
.send-button.stop {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.chat-profile {
  position: sticky;
  top: 25px;
  max-height: 100%;
  overflow-y: auto;
}
.progress-card {
  border-color: var(--accent-line);
  background: linear-gradient(155deg, var(--surface), var(--accent-soft));
}
.chat-progress {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.chat-progress b {
  font-size: 26px;
  font-weight: 500;
}
.progress-track {
  height: 5px;
  border-radius: 5px;
  background: var(--accent-line);
  overflow: hidden;
}
.progress-track i {
  display: block;
  height: 100%;
  border-radius: 5px;
  background: var(--accent);
  transition: width 0.8s var(--ease);
}
.progress-card > a {
  font-size: 12px;
}
.profile-toggle {
  font-size: 12px;
  text-align: left;
}
.chat-note {
  color: var(--muted);
  font-size: 11px;
  padding: 16px;
}
.chat-param-list {
  max-height: 380px;
  overflow: auto;
}
.chat-param-list > div {
  padding: 12px 0;
  border-bottom: 1px solid var(--accent-line);
  font-size: 12px;
}
.chat-param-list span {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.chat-param-list b {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-top: 7px;
  overflow-wrap: anywhere;
}
.form-error {
  margin: 0 20px;
}
@keyframes thinking-pulse {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}
@media (max-width: 1199px) {
  .interview-layout {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 16px;
  }
}
@media (max-width: 767px) {
  .interview-page {
    height: calc(100vh - var(--van-tabbar-height, 56px) - env(safe-area-inset-bottom, 0px));
    height: calc(100dvh - var(--van-tabbar-height, 56px) - env(safe-area-inset-bottom, 0px));
    padding-top: 14px;
    padding-bottom: 12px;
    gap: 12px;
  }
  .interview-layout {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .interview-page :deep(.page-head) {
    position: relative;
  }
  .interview-page :deep(.ph-actions) {
    position: absolute;
    top: 4px;
    right: 0;
    font-size: 13px;
  }
  .chat-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 10px 14px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-line);
    border-radius: 10px;
    font-size: 12px;
    gap: 12px;
  }
  .chat-summary div {
    min-width: 0;
  }
  .chat-summary b {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chat-summary span {
    font-size: 10px;
    color: var(--muted);
  }
  .chat-summary button {
    flex-shrink: 0;
    font-size: 12px;
  }
  .chat-profile {
    display: none;
  }
  .progress-card {
    padding: 16px;
    gap: 10px;
  }
  .progress-card h2 {
    font-size: 16px;
  }
  .chat-note {
    display: none;
  }
  .chat-area {
    width: 100%;
    height: auto;
    flex: 1;
    min-height: 0;
  }
  .chat-head {
    padding: 15px;
  }
  .chat-log {
    padding: 18px 14px;
  }
  .message-bubble {
    padding: 12px 14px;
  }
  .chat-composer {
    margin: 0 12px 14px;
  }
  .composer-actions > span {
    font-size: 9px;
    max-width: 180px;
  }
  .chat-online {
    display: none;
  }
  .chat-welcome {
    padding: 20px 0;
  }
  .chat-welcome h2 {
    font-size: 21px;
  }
}
</style>
