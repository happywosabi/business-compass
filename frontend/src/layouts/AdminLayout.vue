<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminRequest, type AdminSession } from '@/api/admin'
import { errorMessage, ApiError } from '@/api/client'
import CompassMark from '@/components/CompassMark.vue'
import PasswordField from '@/components/PasswordField.vue'

const router = useRouter()
const route = useRoute()
const expires = ref(0)
const checking = ref(true)
const password = ref('')
const error = ref('')
const busy = ref(false)
const now = ref(Date.now())
const unlocked = computed(() => expires.value > now.value)
const remaining = computed(() => `${Math.floor(Math.max(0, expires.value - now.value) / 60000)}:${String(Math.floor(Math.max(0, expires.value - now.value) / 1000) % 60).padStart(2, '0')}`)
const links = [ ['overview', '运行概览', '01'], ['users', '用户管理', '02'], ['runs', 'AI 任务', '03'], ['profiles', '档案诊断', '04'], ['hotspots', '热点来源', '05'], ['audits', '操作审计', '06'], ['system', '系统状态', '07'] ]
let timer: ReturnType<typeof setInterval> | undefined

async function check() {
  try {
    const value = await adminRequest<AdminSession>('/session')
    expires.value = value.unlocked && value.expires_at ? Date.parse(value.expires_at) : 0
  } catch (e) {
    expires.value = 0
    if (e instanceof ApiError && [401, 403].includes(e.status)) await router.replace('/me')
    else error.value = errorMessage(e)
  } finally { checking.value = false }
}
async function unlock() {
  busy.value = true
  error.value = ''
  try {
    const value = await adminRequest<{ expires_at: string }>('/unlock', { password: password.value })
    now.value = Date.now()
    expires.value = Date.parse(value.expires_at)
  } catch (e) { error.value = errorMessage(e) }
  finally { password.value = ''; busy.value = false }
}
async function lock() {
  expires.value = 0
  password.value = ''
  try { await adminRequest('/lock', {}) }
  catch (e) { error.value = errorMessage(e) }
}
function expired() { expires.value = 0; password.value = '' }
function visibility() { if (document.visibilityState === 'visible') { now.value = Date.now(); void check() } }
onMounted(async () => {
  await check()
  timer = setInterval(() => { now.value = Date.now() }, 1000)
  document.addEventListener('visibilitychange', visibility)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('visibilitychange', visibility)
  expires.value = 0
  password.value = ''
  void adminRequest('/lock', {}).catch(() => undefined)
})
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-side">
      <RouterLink to="/admin" class="admin-brand"><CompassMark :size="40" /><span>商业罗盘<small>管理工作台 / CONTROL</small></span></RouterLink>
      <div class="admin-side-label">运营与诊断</div>
      <nav aria-label="管理导航"><RouterLink v-for="[path, label, number] in links" :key="path" :to="`/admin/${path}`" :class="{ selected: route.params.section === path || path === 'overview' && route.path === '/admin' }"><span>{{ number }}</span>{{ label }}<b>↗</b></RouterLink></nav>
      <div class="admin-side-foot"><span class="admin-live-dot" />管理员专用空间<RouterLink to="/me">返回我的账号 →</RouterLink></div>
    </aside>
    <main class="admin-main">
      <header class="admin-top"><span>BUSINESS COMPASS <i>/</i> 管理中心</span><button v-if="unlocked" class="admin-lock" @click="lock">{{ remaining }} 后锁定 · 立即锁定</button><RouterLink v-else to="/me">返回应用 ↗</RouterLink></header>
      <div v-if="checking" class="admin-gate bc-card" role="status">正在验证管理权限…</div>
      <section v-else-if="!unlocked" class="admin-gate bc-card">
        <CompassMark :size="80" />
        <p class="admin-eyebrow">SECURE WORKSPACE</p>
        <h1>验证身份，进入工作台</h1>
        <p>输入当前账号密码。本次管理权限有效期为 15 分钟。</p>
        <form @submit.prevent="unlock">
          <PasswordField v-model="password" label="账号密码" name="admin-password" autocomplete="current-password" />
          <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
          <van-button native-type="submit" type="primary" block :loading="busy">解锁管理工作台</van-button>
        </form>
        <button class="admin-text-button" @click="check">重新检查权限</button>
      </section>
      <RouterView v-else v-slot="{ Component }"><component :is="Component" :key="route.fullPath" @locked="expired" /></RouterView>
    </main>
  </div>
</template>

<style>
.admin-shell { min-height: 100dvh; display: grid; grid-template-columns: 240px minmax(0, 1fr); }
.admin-side { background: var(--side); color: var(--side-ink); padding: 32px 20px; display: flex; flex-direction: column; position: sticky; top: 0; height: 100dvh; background-image: linear-gradient(var(--side-grid) 1px, transparent 1px), linear-gradient(90deg,var(--side-grid) 1px,transparent 1px); background-size: 36px 36px; }
.admin-brand { display: flex; gap: 12px; align-items: center; font-size: 20px; font-weight: 650; text-decoration: none; color: inherit; }
.admin-brand small { display: block; font-size: 10px; letter-spacing: .1em; font-weight: 400; color: var(--side-muted); margin-top: 6px; }
.admin-side-label { font-size: 11px; color: var(--side-muted); letter-spacing: .15em; margin: 52px 12px 18px; }
.admin-side nav { display: grid; gap: 8px; }
.admin-side nav a { display: flex; align-items: center; gap: 14px; color: var(--side-ink); text-decoration: none; padding: 14px 12px; border-radius: 8px; transition: background .25s, transform .25s; }
.admin-side nav a span { font-family: var(--font-num); font-size: 12px; color: var(--side-muted); }
.admin-side nav a b { margin-left: auto; opacity: 0; color: var(--accent-line); transition: opacity .25s; }
.admin-side nav a:hover { background: var(--side-hover); transform: translateX(3px); }
.admin-side nav a.selected { background: var(--side-active); box-shadow: inset 3px 0 var(--accent); }
.admin-side nav a.selected b { opacity: 1; }
.admin-side-foot { margin-top: auto; padding: 28px 12px 0; color: var(--side-muted); font-size: 12px; border-top: 1px solid var(--side-line); }
.admin-side-foot a { display: block; margin-top: 16px; color: var(--side-ink); }
.admin-live-dot { display: inline-block; width: 6px; height: 6px; background: var(--accent-line); border-radius: 50%; margin-right: 8px; box-shadow: 0 0 0 4px var(--side-hover); }
.admin-main { min-width: 0; padding: 0 40px 48px; }
.admin-top { height: 82px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); margin-bottom: 34px; gap: 16px; font-size: 11px; letter-spacing: .05em; color: var(--muted); }
.admin-top i { margin: 0 14px; color: var(--accent); }
.admin-lock,.admin-text-button { background: transparent; border: 0; color: var(--accent-ink); cursor: pointer; padding: 10px 0; }
.admin-gate { margin: 9vh auto; max-width: 480px; padding: 40px; text-align: center; animation: admin-enter .45s var(--ease) both; }
.admin-gate h1 { font-size: 25px; margin: 16px 0; }
.admin-gate p { font-size: 14px; color: var(--muted); line-height: 1.8; }
.admin-gate form { margin: 28px 0 12px; text-align: left; }
.admin-gate .van-button { margin-top: 20px; }
.admin-eyebrow { font-family: var(--font-num); font-size: 12px!important; letter-spacing: .2em; color: var(--accent-ink)!important; }
.admin-error { color: var(--bad)!important; background: var(--bad-soft); padding: 12px 16px; border-radius: 8px; }
@keyframes admin-enter { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@media(max-width: 1000px) { .admin-shell { grid-template-columns: 196px minmax(0, 1fr); } .admin-main { padding: 0 24px 32px; } .admin-side { padding: 26px 14px; } }
@media(max-width: 720px) { .admin-shell { display: block; } .admin-side { position: static; height: auto; padding: 18px 16px 0; } .admin-brand { font-size: 17px; } .admin-brand small { font-size: 9px; } .admin-side-label,.admin-side-foot { display: none; } .admin-side nav { display: flex; overflow-x: auto; margin: 18px -16px 0; padding: 0 12px 12px; gap: 4px; } .admin-side nav a { white-space: nowrap; font-size: 13px; padding: 10px; } .admin-side nav a span,.admin-side nav a b { display: none; } .admin-side nav a.selected { box-shadow: inset 0 -2px var(--accent); } .admin-main { padding: 0 16px 28px; } .admin-top { height: 64px; margin-bottom: 24px; } .admin-top>span { font-size: 9px; max-width: 110px; line-height: 1.8; } .admin-top i { margin: 0 4px; } .admin-gate { margin: 30px auto; padding: 28px 20px; } }
@media(prefers-reduced-motion: reduce) { .admin-shell *, .admin-shell *::before, .admin-shell *::after { animation: none!important; transition: none!important; } }
</style>
