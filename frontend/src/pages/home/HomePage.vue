<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { profilesApi, type Profile, type View, type Template } from '@/api/profiles'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import CompassMark from '@/components/CompassMark.vue'
import PageHead from '@/components/PageHead.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import { PROFILE_STAGES } from '@/utils/parameters'
import { formatDate } from '@/utils/format'

const templates = ref<Template[]>([])
const totalFor = (p: Profile) =>
  templates.value.find((t) => t.key === p.template_key)?.quick_required_keys?.length ?? 0
const profiles = ref<Profile[]>([]),
  view = ref<View>('active'),
  loading = ref(true),
  error = ref('')
const greeting = computed(() =>
  profiles.value.length ? '每个好生意，都从算清楚开始。' : '你的下一个好生意，从这里启航。',
)
let sequence = 0
async function load() {
  const ticket = ++sequence
  loading.value = true
  error.value = ''
  try {
    const [items, metadata] = await Promise.all([
      profilesApi.list(view.value),
      profilesApi.templates(),
    ])
    templates.value = metadata
    if (ticket === sequence) profiles.value = items
  } catch (e) {
    if (ticket === sequence) error.value = errorMessage(e)
  } finally {
    if (ticket === sequence) loading.value = false
  }
}
async function restore(profile: Profile) {
  try {
    await profilesApi.restore(profile.id, profile.revision)
    await load()
  } catch (e) {
    error.value = errorMessage(e)
  }
}
watch(view, load)
onMounted(load)
</script>
<template>
  <div class="page home-page">
    <PageHead title="我的档案"
      ><template #actions
        ><van-button type="primary" to="/profiles/new"
          ><span class="button-content"
            ><AppIcon name="plus" :size="17" />新建档案</span
          ></van-button
        ></template
      ></PageHead
    >
    <section class="voyage-banner">
      <div class="banner-orbit" aria-hidden="true"><span /><span /><span /></div>
      <div class="banner-copy">
        <span class="eyebrow">BUSINESS COMPASS / 商业罗盘</span>
        <h2>{{ greeting }}</h2>
        <p>把想法变成看得见的数字，把不确定留给下一次验证。</p>
        <div class="banner-footer">
          <span class="live-dot" /> 一份档案，一家店，一步更有把握的决定
        </div>
      </div>
      <CompassMark :size="145" dark motion="settle" hover-sway />
    </section>
    <div class="section-bar">
      <div class="segmented" aria-label="档案分类">
        <button
          v-for="(label, key) in { active: '进行中', archived: '已归档', deleted: '最近删除' }"
          :key="key"
          type="button"
          :aria-pressed="view === key"
          :class="{ active: view === key }"
          @click="view = key as View"
        >
          {{ label }}
        </button>
      </div>
      <span class="sub"><AnimatedNumber :value="profiles.length" /> 份档案</span>
    </div>
    <p v-if="error" class="form-error" role="alert">
      {{ error }} <button class="text-link" @click="load">重试</button>
    </p>
    <div v-if="loading" class="profile-grid" aria-label="正在加载档案">
      <div v-for="i in 3" :key="i" class="skeleton-card bc-card">
        <div class="skeleton" />
        <div class="skeleton short" />
        <div class="skeleton tall" />
      </div>
    </div>
    <TransitionGroup v-else name="list" tag="div" class="profile-grid">
      <article
        v-for="(profile, i) in profiles"
        :key="profile.id"
        class="profile-card bc-card"
        :style="{ '--order': i }"
      >
        <div class="profile-card-head">
          <span class="profile-symbol"><AppIcon name="profiles" :size="22" /></span
          ><span class="profile-status" :class="{ ready: !profile.quick_missing.length }">{{
            profile.deleted_at
              ? '30 天内可恢复'
              : profile.status === 'archived'
                ? '已归档'
                : profile.quick_missing.length
                  ? '正在完善'
                  : '可以测算'
          }}</span>
        </div>
        <h2>{{ profile.name }}</h2>
        <p class="sub">
          {{ profile.city }} · {{ profile.template_key === 'orchard' ? '果园' : '饮品' }} ·
          {{ PROFILE_STAGES[profile.stage] }}
        </p>
        <div class="mini-route">
          <span
            v-for="n in totalFor(profile)"
            :key="n"
            :class="{ filled: n <= totalFor(profile) - profile.quick_missing.length }"
          />
        </div>
        <p class="progress-copy">
          {{
            profile.quick_missing.length
              ? `再填 ${profile.quick_missing.length} 项，就能先算一下`
              : '关键数字已就绪，看看这家店的可能性'
          }}
        </p>
        <footer>
          <span class="sub">{{ formatDate(profile.updated_at) }}</span
          ><button
            v-if="view === 'deleted'"
            type="button"
            class="text-link"
            @click="restore(profile)"
          >
            恢复档案 ↗</button
          ><RouterLink v-else :to="`/profiles/${profile.id}`" class="card-open"
            >{{ view === 'archived' ? '查看档案' : '继续完善' }}
            <AppIcon name="chevron-right" :size="16"
          /></RouterLink>
        </footer>
      </article>
      <RouterLink v-if="view === 'active'" key="new" to="/profiles/new" class="new-card"
        ><span class="new-plus"><AppIcon name="plus" :size="28" /></span>
        <h2>{{ profiles.length ? '再探索一个想法' : '建第一份档案' }}</h2>
        <p>一个铺面，一种方案。<br />先记下来，再把账算清楚。</p>
        <span class="text-link">新建档案 ↗</span></RouterLink
      >
      <div v-if="!profiles.length && view !== 'active'" key="empty" class="bc-card empty">
        <CompassMark :size="70" />
        <h2>{{ view === 'deleted' ? '这里还没有删除的档案' : '这里还没有归档的档案' }}</h2>
        <p class="sub">
          {{
            view === 'deleted'
              ? '删除后 30 天内可以在这里恢复。'
              : '暂时放下的想法，可以归档后再回来看看。'
          }}
        </p>
      </div>
    </TransitionGroup>
    <div class="journey-note">
      <span class="note-line" /><span>想得再远，也从一个真实的数字开始。</span
      ><span class="note-line" />
    </div>
  </div>
</template>
<style scoped>
.voyage-banner {
  position: relative;
  overflow: hidden;
  border-radius: 14px;
  padding: 28px 24px;
  color: var(--side-ink);
  background: var(--side);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  animation: compass-rise 0.55s var(--ease) both;
}
.banner-copy {
  z-index: 1;
}
.banner-copy .eyebrow {
  color: var(--side-muted);
  font-size: 10px;
  letter-spacing: 0.15em;
}
.banner-copy h2 {
  font-size: 25px;
  margin: 10px 0;
  line-height: 1.5;
}
.banner-copy p {
  color: var(--side-muted);
  font-size: 13px;
}
.banner-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--side-muted);
  margin-top: 26px;
}
.voyage-banner > svg {
  flex: none;
  z-index: 1;
}
.banner-orbit {
  position: absolute;
  right: 15px;
  top: 50%;
  width: 400px;
  height: 400px;
  transform: translate(20%, -50%);
  pointer-events: none;
}
.banner-orbit span {
  border: 1px solid var(--side-line);
  position: absolute;
  inset: 0;
  border-radius: 50%;
}
.banner-orbit span:nth-child(2) {
  inset: 45px;
}
.banner-orbit span:nth-child(3) {
  inset: 90px;
}
.section-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
  gap: 18px;
}
.profile-card {
  animation: compass-rise 0.5s calc(var(--order) * 65ms) var(--ease) both;
  gap: 10px;
  position: relative;
  transition:
    transform 0.25s var(--ease),
    box-shadow 0.25s,
    border-color 0.25s;
}
.profile-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-card);
  border-color: var(--accent-line);
}
.profile-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.profile-symbol {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.profile-status {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface-2);
  padding: 3px 9px;
  border-radius: 20px;
}
.profile-status.ready {
  background: var(--good-soft);
  color: var(--good);
}
.profile-card h2 {
  font-size: 20px;
}
.profile-card footer {
  margin-top: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.profile-card footer .sub {
  font-size: 11px;
}
.mini-route {
  display: flex;
  gap: 5px;
  margin-top: 14px;
}
.mini-route span {
  flex: 1;
  height: 4px;
  background: var(--line-soft);
  border-radius: 4px;
  transition: background 0.4s;
}
.mini-route span.filled {
  background: var(--accent);
}
.progress-copy {
  font-size: 12px;
  color: var(--muted);
}
.card-open {
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
}
.card-open::after {
  content: '';
  position: absolute;
  inset: 0;
}
.new-card {
  min-height: 290px;
  border: 1px dashed var(--accent-line);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--muted);
  text-decoration: none;
  text-align: center;
  background: linear-gradient(145deg, var(--surface-2), var(--accent-soft));
  transition:
    background 0.25s,
    transform 0.25s;
  animation: compass-rise 0.6s 0.1s both;
}
.new-card:hover {
  transform: translateY(-4px);
}
.new-card h2 {
  color: var(--ink);
  font-size: 17px;
}
.new-card p {
  font-size: 13px;
}
.new-plus {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  border: 1px solid var(--accent-line);
  color: var(--accent-ink);
  display: grid;
  place-items: center;
  transition: transform 0.4s var(--spring);
}
.new-card:hover .new-plus {
  transform: rotate(90deg);
}
.new-card .text-link {
  font-size: 13px;
}
.empty {
  align-items: center;
  text-align: center;
  padding: 35px;
  grid-column: 1/-1;
}
.journey-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--faint);
  font-size: 11px;
  margin-top: 12px;
}
.note-line {
  height: 1px;
  background: var(--line);
  width: 50px;
}
.skeleton-card {
  min-height: 290px;
}
.skeleton {
  height: 24px;
}
.skeleton.short {
  width: 60%;
  height: 14px;
}
.skeleton.tall {
  height: 90px;
  margin-top: 20px;
}
@media (min-width: 1200px) {
  .voyage-banner {
    padding: 34px;
  }
  .banner-copy h2 {
    font-size: 29px;
  }
}
@media (max-width: 767px) {
  .voyage-banner > svg {
    position: absolute;
    right: -25px;
    top: 15px;
    width: 120px;
    opacity: 0.22;
  }
  .banner-copy h2 {
    font-size: 23px;
    max-width: 11em;
  }
  .banner-copy p {
    max-width: 20em;
  }
  .banner-footer {
    font-size: 10px;
  }
  .journey-note {
    font-size: 10px;
    gap: 8px;
  }
  .note-line {
    width: 20px;
  }
}
</style>
