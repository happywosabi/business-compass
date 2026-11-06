<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { adminRequest, queryString, userState, type AdminAudit, type AdminCollection, type AdminHotspot, type AdminProfile, type AdminRun, type AdminUser, type Overview, type Page, type SystemState } from '@/api/admin'
import { ApiError, errorMessage } from '@/api/client'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import MarkdownText from '@/components/MarkdownText.vue'

const emit = defineEmits<{ locked: [] }>()
const route = useRoute()
const section = computed(() => String(route.params.section || 'overview'))
const titles: Record<string, [string, string]> = {
  overview: ['运行概览', '掌握使用情况，让每一次运营都有方向。'], users: ['用户管理', '管理账号状态与个人 AI 额度。'],
  runs: ['AI 任务', '查看任务用量、处理状态与异常。'], profiles: ['档案诊断', '按需查看资料，帮助用户定位问题。'],
  hotspots: ['热点来源', '维护推荐内容，人工下架独立于自动采集。'], audits: ['操作审计', '每一次管理操作，都留下可追溯的记录。'], system: ['系统状态', '应用、模型配置与后台任务的健康情况。'],
}
const title = computed(() => titles[section.value] || titles.overview!)
const overview = ref<Overview | null>(null)
const system = ref<SystemState | null>(null)
const users = ref<AdminUser[]>([])
const runs = ref<AdminRun[]>([])
const profiles = ref<AdminProfile[]>([])
const hotspots = ref<AdminHotspot[]>([])
const collections = ref<AdminCollection[]>([])
const hotView = ref('hotspots')
const audits = ref<AdminAudit[]>([])
const cursor = ref<string | null>(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const search = ref('')
const filter = ref('')
const kind = ref('')
const model = ref('')
const userId = ref('')
const verified = ref('')
const since = ref('')
const until = ref('')
const actor = ref('')
const target = ref('')
const days = ref(7)
const controller = new AbortController()
let alive = true
let requestVersion = 0
const listSection = computed(() => section.value === 'hotspots' ? hotView.value : section.value)
const activeRows = computed(() => ({ users: users.value, runs: runs.value, profiles: profiles.value, hotspots: hotspots.value, collections: collections.value, audits: audits.value })[listSection.value] || [])
const statusLabels: Record<string, string> = { active: '正常', disabled: '已停用', running: '进行中', succeeded: '已完成', failed: '失败', cancelled: '已取消', success: '成功', draft: '草稿', archived: '已归档', idea: '构想', preparing: '筹备中', operating: '经营中' }
const labels = (value: string) => statusLabels[value] || value
const sourceNames: Record<string, string> = { chinanews_life: '中新网·生活', chinanews_finance: '中新网·财经', chinanews_latest: '中新网·即时', foodmate: '食品伙伴网', dailyhot: '可选热点聚合源' }
const sourceStatuses: Record<string, string> = { ok: '读取成功', redirect: '重定向已拒绝', http_error: 'HTTP 请求失败', timeout: '读取超时', network_error: '网络连接失败', format_error: '格式无效', oversized: '响应超限', encoding_error: '传输编码不支持' }
const collectionStages: Record<string, string> = { sources: '读取来源', classification: '模型筛选', embedding: '向量去重', publishing: '保存候选', completed: '已完成' }
const number = (value: number) => value.toLocaleString('zh-CN')
const date = (value: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'
const bytes = (value: number) => `${(value / 1024 / 1024).toFixed(2)} MiB`
const maxRuns = computed(() => Math.max(1, ...overview.value?.trend.map(d => d.runs) || []))
const stats = computed(() => overview.value ? [
  { label: '累计用户', value: overview.value.totals.users, note: '当前注册账号', accent: false },
  { label: '商业档案', value: overview.value.totals.profiles, note: '当前有效档案', accent: false },
  { label: 'AI 完成任务', value: overview.value.totals.succeeded, note: `${days.value} 天内成功完成`, accent: true },
  { label: '测算请求', value: overview.value.totals.calculations, note: `${days.value} 天内预约次数，含失败`, accent: false },
] : [])

async function call<T>(path: string, body?: unknown): Promise<T> {
  try { return await adminRequest<T>(path, body, controller.signal) }
  catch (e) {
    if (e instanceof ApiError && [401, 403, 423].includes(e.status)) { clear(); emit('locked') }
    throw e
  }
}
function clear() {
  users.value = []; runs.value = []; profiles.value = []; hotspots.value = []; collections.value = []; audits.value = []
  sensitive.value = null; overview.value = null; system.value = null; dialog.value = null
}
async function load(more = false) {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    if (section.value === 'overview') {
      const result = await call<Overview>(`/overview?days=${days.value}`)
      if (alive && version === requestVersion) overview.value = result
    } else if (section.value === 'system') {
      const result = await call<SystemState>('/system')
      if (alive && version === requestVersion) system.value = result
    }
    else {
      const params: Record<string, string | number | undefined> = { cursor: more ? cursor.value || undefined : undefined }
      if (section.value === 'users') Object.assign(params, { q: search.value, status: filter.value, verified: verified.value })
      if (['runs', 'profiles'].includes(section.value)) params.user_id = userId.value
      if (section.value === 'runs') Object.assign(params, { status: filter.value, kind: kind.value, model: model.value })
      if (['runs', 'audits'].includes(section.value)) Object.assign(params, { since: since.value ? new Date(`${since.value}T00:00:00+08:00`).toISOString() : '', until: until.value ? new Date(new Date(`${until.value}T00:00:00+08:00`).getTime()+86400000).toISOString() : '' })
      if (section.value === 'audits') Object.assign(params, { action: search.value, actor_id: actor.value, target: target.value, result: filter.value })
      const result = await call<Page<AdminUser | AdminRun | AdminProfile | AdminHotspot | AdminCollection | AdminAudit>>(`/${listSection.value}${queryString(params)}`)
      if (!alive || version !== requestVersion) return
      cursor.value = result.next_cursor
      if (section.value === 'users') users.value = [...(more ? users.value : []), ...result.items as AdminUser[]]
      if (section.value === 'runs') runs.value = [...(more ? runs.value : []), ...result.items as AdminRun[]]
      if (section.value === 'profiles') profiles.value = [...(more ? profiles.value : []), ...result.items as AdminProfile[]]
      if (listSection.value === 'hotspots') hotspots.value = [...(more ? hotspots.value : []), ...result.items as AdminHotspot[]]
      if (listSection.value === 'collections') collections.value = [...(more ? collections.value : []), ...result.items as AdminCollection[]]
      if (section.value === 'audits') audits.value = [...(more ? audits.value : []), ...result.items as AdminAudit[]]
    }
  } catch (e) { if (alive) error.value = errorMessage(e) }
  finally { if (alive && version === requestVersion) loading.value = false }
}
function changeHotView() {
  hotspots.value = []; collections.value = []; cursor.value = null
  void load()
}

interface Dialog { title: string; description: string; path: string; data: Record<string, unknown>; quota?: boolean; inspect?: boolean }
const dialog = ref<Dialog | null>(null)
const reason = ref('')
const quota = ref('')
const dialogError = ref('')
const submitting = ref(false)
const selectedProfile = ref<AdminProfile | null>(null)
const inspectSection = ref('parameters')
const inspectOptions = [['parameters', '档案参数'], ['history', '修改记录'], ['evaluations', '测算快照'], ['chat', '用户对话'], ['reports', 'AI 解读'], ['copy', '创作文案']]
const sensitive = ref<unknown>(null)
const sensitiveCursor = ref<string | null>(null)
const inspectReason = ref('')
const sensitiveItems = computed(() => {
  const value = sensitive.value as { items?: Record<string, unknown>[] } | null
  return value?.items || null
})
function open(value: Dialog) { dialog.value = value; reason.value = ''; dialogError.value = ''; quota.value = '' }
function userAction(user: AdminUser, action: string) {
  const names: Record<string, string> = { disable: '停用账号', enable: '启用账号', unlock: '解除登录锁定', revoke_sessions: '撤销全部会话', quota: '调整 AI 日额度' }
  quota.value = user.daily_ai_quota === null ? '' : String(user.daily_ai_quota)
  const value = quota.value
  open({ title: names[action]!, description: `${user.email} · ${action === 'disable' ? '将退出所有设备并取消正在执行的 AI 任务。' : action === 'quota' ? '0 表示关闭 AI，新额度只影响后续任务；留空使用系统默认值。' : '请确认操作对象和原因。'}`, path: `/users/${user.id}/actions`, data: { action, expected: userState(user) }, quota: action === 'quota' })
  quota.value = value
}
function inspect(profile: AdminProfile) {
  selectedProfile.value = profile
  sensitive.value = null
  open({ title: '查看用户资料', description: `${profile.name} · 本次查看会记录原因，资料只读。`, path: `/profiles/${profile.id}/inspect`, data: {}, inspect: true })
}
async function submit() {
  if (!dialog.value || submitting.value) return
  if (reason.value.trim().length < 5) { dialogError.value = '请填写至少 5 字的具体原因'; return }
  submitting.value = true
  dialogError.value = ''
  try {
    const data = { ...dialog.value.data, reason: reason.value.trim() }
    if (dialog.value.quota) {
      const value = quota.value.trim() === '' ? null : Number(quota.value)
      if (value !== null && (!Number.isInteger(value) || value < 0 || value > 1000)) throw new ApiError(422, '日额度需为 0–1000 的整数')
      Object.assign(data, { quota: value })
    }
    if (dialog.value.inspect) Object.assign(data, { section: inspectSection.value })
    const result = await call<unknown>(dialog.value.path, data)
    if (!alive) return
    if (dialog.value?.inspect) {
      sensitive.value = result
      sensitiveCursor.value = (result as { next_cursor?: string | null }).next_cursor || null
      inspectReason.value = reason.value.trim()
    } else { notice.value = '操作已完成并写入审计记录'; await load() }
    dialog.value = null
  } catch (e) { if (alive) dialogError.value = errorMessage(e) }
  finally { if (alive) submitting.value = false }
}
async function moreSensitive() {
  if (!selectedProfile.value || !sensitiveCursor.value || submitting.value) return
  submitting.value = true
  try {
    const result = await call<Page<Record<string, unknown>>>(`/profiles/${selectedProfile.value.id}/inspect`, { reason: inspectReason.value, section: inspectSection.value, cursor: sensitiveCursor.value })
    if (!alive) return
    sensitive.value = { items: [...sensitiveItems.value || [], ...result.items] }
    sensitiveCursor.value = result.next_cursor
  } catch (e) { error.value = errorMessage(e) }
  finally { submitting.value = false }
}
function closeSensitive() { sensitive.value = null; sensitiveCursor.value = null; selectedProfile.value = null; inspectReason.value = '' }
function pretty(value: unknown) { return JSON.stringify(value, null, 2) }
onMounted(() => void load())
onBeforeUnmount(() => { alive = false; controller.abort(); clear(); reason.value = ''; inspectReason.value = '' })
</script>

<template>
  <div class="admin-page">
    <div class="admin-page-head"><div><p class="admin-eyebrow">{{ section === 'overview' ? 'YOUR BUSINESS, IN VIEW' : 'OPERATIONS / '+section.toUpperCase() }}</p><h1>{{ title[0] }}</h1><p>{{ title[1] }}</p></div><div class="admin-head-actions"><select v-if="section === 'overview'" v-model="days" aria-label="统计时间范围" @change="load()"><option :value="7">近 7 天</option><option :value="30">近 30 天</option></select><button class="admin-button" :disabled="loading" @click="load()">{{ loading ? '加载中…' : '↻ 刷新' }}</button></div></div>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button class="admin-text-button" @click="load()">重试</button></p>
    <p v-if="notice" class="admin-notice" role="status">{{ notice }}</p>
    <template v-if="section === 'overview' && overview">
      <div class="admin-stats"><article v-for="(stat, i) in stats" :key="stat.label" class="bc-card admin-stat" :class="{ 'admin-stat-accent': stat.accent }" :style="{ animationDelay: `${i*60}ms` }"><div><span>{{ stat.label }}</span><span class="admin-stat-index">0{{ i+1 }}</span></div><AnimatedNumber :value="stat.value" /><p>{{ stat.note }}</p></article></div>
      <section class="bc-card admin-trend"><div class="admin-panel-title"><div><p class="admin-eyebrow">ACTIVITY</p><h2>AI 使用趋势</h2></div><span class="admin-pill">北京时间 · {{ days }} 天</span></div><div class="admin-chart" role="img" :aria-label="`最近${days}天的AI任务趋势`"><div v-for="(point, i) in overview.trend" :key="point.date" class="admin-bar-column" tabindex="0" :aria-label="`${point.date}：${point.runs}次，失败${point.failed}次，${point.tokens}tokens`" :style="{ '--delay': `${i*18}ms` }"><div class="admin-chart-tip">{{ point.date }}<br>{{ point.runs }} 次 · {{ number(point.tokens) }} tokens<br>失败 {{ point.failed }} 次</div><span class="admin-bar-value">{{ point.runs }}</span><div class="admin-bar" :style="{ height: `${Math.max(2, point.runs/maxRuns*150)}px` }"><div v-if="point.failed" :style="{ height: `${point.failed/Math.max(1,point.runs)*100}%` }" /></div><span class="admin-bar-date">{{ i % (days === 30 ? 5 : 1) === 0 ? point.date.slice(5) : '' }}</span></div></div><p class="admin-chart-legend"><i />任务数 <i class="failed" />失败数</p></section>
      <div class="admin-overview-bottom"><section class="bc-card admin-panel"><p class="admin-eyebrow">SERVICE QUALITY</p><h2>任务质量与用量</h2><strong class="admin-rate">{{ overview.totals.success_rate === null ? '—' : `${(overview.totals.success_rate*100).toFixed(1)}%` }}<small>成功率</small></strong><p class="admin-muted">成功 ÷（成功 + 失败）；取消和进行中单独展示。tokens 为已记录用量，未返回用量不代表零费用。</p><dl class="admin-dl"><div><dt>失败 / 取消 / 进行中</dt><dd>{{ overview.totals.failed }} / {{ overview.totals.cancelled }} / {{ overview.totals.running }}</dd></div><div><dt>已记录输入 tokens</dt><dd>{{ number(overview.totals.input_tokens) }}</dd></div><div><dt>已记录输出 tokens</dt><dd>{{ number(overview.totals.output_tokens) }}</dd></div></dl></section><section class="bc-card admin-panel"><p class="admin-eyebrow">PUBLIC SOURCES</p><h2>公共热点独立预算</h2><p class="admin-muted">公共采集用量单列，不计入个人 AI 任务。</p><dl class="admin-dl"><div><dt>采集任务</dt><dd>{{ overview.public_hotspots.runs }}</dd></div><div><dt>已记录模型 tokens</dt><dd>{{ number(overview.public_hotspots.llm_tokens) }}</dd></div><div><dt>已记录向量 tokens</dt><dd>{{ number(overview.public_hotspots.embedding_tokens) }}</dd></div></dl><RouterLink to="/admin/hotspots" class="admin-inline-link">管理热点来源 ↗</RouterLink></section></div>
    </template>
    <template v-if="section === 'system' && system">
      <div class="admin-stats"><article class="bc-card admin-stat"><div>数据库<span class="admin-pill good">正常</span></div><strong class="admin-status-large">已连接</strong><p>应用 {{ system.version }}</p></article><article class="bc-card admin-stat"><div>定时任务<span class="admin-pill" :class="system.worker.stale ? 'bad' : 'good'">{{ system.worker.stale ? '需检查' : '正常' }}</span></div><strong class="admin-status-large">{{ system.worker.stale ? '心跳过期' : '运行中' }}</strong><p>最近心跳 {{ date(system.worker.last_seen) }}</p></article></div>
      <div class="admin-overview-bottom"><section class="bc-card admin-panel"><p class="admin-eyebrow">CONFIGURATION</p><h2>模型与服务</h2><dl class="admin-dl"><div v-for="(value, key) in system.models" :key="key"><dt>{{ { interview: '访谈', report: '报告', embedding: '向量' }[key] || key }}</dt><dd>{{ value }}</dd></div><div v-for="(value, key) in system.configured" :key="key"><dt>{{ { ai: 'AI 密钥', embedding: '向量密钥', mail: '邮件服务' }[key] || key }}</dt><dd><span class="admin-pill" :class="value ? 'good' : 'bad'">{{ value ? '已配置' : '未配置' }}</span></dd></div></dl></section><section class="bc-card admin-panel"><p class="admin-eyebrow">COLLECTION</p><h2>最近采集</h2><dl class="admin-dl"><div><dt>状态</dt><dd>{{ system.last_collection ? labels(system.last_collection.status) : '尚无采集记录' }}</dd></div><div><dt>开始时间</dt><dd>{{ date(system.last_collection?.created_at || null) }}</dd></div><div><dt>完成时间</dt><dd>{{ date(system.last_collection?.finished_at || null) }}</dd></div><div><dt>个人默认额度</dt><dd>{{ system.default_daily_ai_quota }} 次/天</dd></div><div><dt>公共采集上限</dt><dd>{{ system.public_hot_daily_limit }} 次/天</dd></div></dl></section></div>
    </template>
    <template v-if="!['overview', 'system'].includes(section)">
      <div v-if="section === 'hotspots'" class="bc-card admin-filters"><label>查看<select v-model="hotView" aria-label="热点记录类型" @change="changeHotView"><option value="hotspots">热点来源</option><option value="collections">公共采集记录</option></select></label></div>
      <form v-if="section !== 'hotspots'" class="bc-card admin-filters" @submit.prevent="load()">
        <input v-if="['users','audits'].includes(section)" v-model="search" :placeholder="section === 'users' ? '搜索邮箱或昵称' : '操作类型，如 user.disable'" :aria-label="section === 'users' ? '搜索邮箱或昵称' : '操作类型'">
        <input v-if="['runs','profiles'].includes(section)" v-model="userId" placeholder="用户 ID（可选）" aria-label="用户ID">
        <select v-if="section === 'users'" v-model="filter" aria-label="账号状态"><option value="">全部账号状态</option><option value="active">正常</option><option value="disabled">已停用</option></select>
        <select v-if="section === 'users'" v-model="verified" aria-label="邮箱验证"><option value="">全部验证状态</option><option value="true">已验证</option><option value="false">未验证</option></select>
        <template v-if="section === 'runs'"><select v-model="filter" aria-label="任务状态"><option value="">全部任务状态</option><option v-for="s in ['running','succeeded','failed','cancelled']" :key="s" :value="s">{{ labels(s) }}</option></select><select v-model="kind" aria-label="任务类型"><option value="">全部任务类型</option><option value="interview">访谈</option><option value="report">报告</option><option value="content">文案</option></select><input v-model="model" placeholder="模型名称" aria-label="模型名称"><label>从<input v-model="since" type="date" aria-label="开始日期"></label><label>至<input v-model="until" type="date" aria-label="结束日期"></label></template>
        <template v-if="section === 'audits'"><label>从<input v-model="since" type="date" aria-label="开始日期"></label><label>至<input v-model="until" type="date" aria-label="结束日期"></label><input v-model="actor" placeholder="操作人 ID" aria-label="操作人ID"><input v-model="target" placeholder="操作对象 ID" aria-label="操作对象ID"><select v-model="filter" aria-label="操作结果"><option value="">全部结果</option><option value="success">成功</option><option value="failed">失败</option></select></template>
        <button class="admin-button primary" :disabled="loading">筛选</button>
      </form>
      <section class="bc-card admin-list" :aria-busy="loading">
        <div class="admin-list-heading"><h2>{{ listSection === 'collections' ? '公共采集记录' : title[0] }}</h2><span class="admin-muted">已载入 {{ activeRows.length }} 条</span></div>
        <p v-if="loading && !activeRows.length" class="admin-empty" role="status">正在读取记录…</p>
        <p v-else-if="!activeRows.length && !error" class="admin-empty">暂无符合条件的记录</p>
        <div v-if="users.length" class="admin-table-wrap"><table><thead><tr><th>账号</th><th>状态</th><th>档案 / 存储</th><th>注册 / 最近登录</th><th>管理</th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td data-label="账号"><strong>{{ user.email }}</strong><small>{{ user.nickname || user.id }} <span v-if="user.is_admin">· 管理员</span></small></td><td data-label="状态"><span class="admin-pill" :class="user.status === 'active' ? 'good' : 'bad'">{{ labels(user.status) }}</span><small>{{ user.verified ? '邮箱已验证' : '邮箱未验证' }} · 今日 AI {{ user.today_ai_runs }} / {{ user.daily_ai_limit }} 次{{ user.daily_ai_quota === null ? '（默认）' : '' }}<br>{{ user.locked_until ? `锁定至 ${date(user.locked_until)}` : '无登录锁定' }}</small></td><td data-label="档案 / 存储">{{ user.profile_count }} 份<small>{{ bytes(user.storage_bytes) }} / {{ bytes(user.storage_limit) }}</small></td><td data-label="时间">{{ date(user.created_at) }}<small>{{ date(user.last_login_at) }}</small></td><td class="admin-row-actions" data-label="管理"><button @click="userAction(user, user.status === 'active' ? 'disable' : 'enable')">{{ user.status === 'active' ? '停用' : '启用' }}</button><button @click="userAction(user, 'quota')">日额度</button><button @click="userAction(user, 'unlock')">解锁</button><button @click="userAction(user, 'revoke_sessions')">退出所有设备</button></td></tr></tbody></table></div>
        <div v-if="runs.length" class="admin-table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>已记录用量 / 耗时</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="run in runs" :key="run.id"><td data-label="任务"><strong>{{ { interview: 'AI 访谈', content: '文案创作', report: '报告解读' }[run.kind] || run.kind }}</strong><small>{{ run.model }}<br>用户 {{ run.user_id }}<br>任务 {{ run.id }}</small></td><td data-label="状态"><span class="admin-pill" :class="run.status === 'failed' ? 'bad' : run.status === 'succeeded' ? 'good' : ''">{{ labels(run.status) }}</span><small v-if="run.error">{{ run.error }}</small></td><td data-label="已记录用量 / 耗时">{{ number(run.input_tokens) }} 入 / {{ number(run.output_tokens) }} 出<small>{{ run.duration_seconds }} 秒</small></td><td data-label="创建时间">{{ date(run.created_at) }}</td><td data-label="操作"><button v-if="run.status === 'running'" class="admin-inline-link" @click="open({ title: '取消 AI 任务', description: '已保存的数据和用量记录会保留。', path: `/runs/${run.id}/cancel`, data: {} })">取消任务</button><span v-else class="admin-muted">已结束</span></td></tr></tbody></table></div>
        <div v-if="profiles.length" class="admin-table-wrap"><table><thead><tr><th>档案</th><th>归属</th><th>状态</th><th>创建时间</th><th>诊断</th></tr></thead><tbody><tr v-for="profile in profiles" :key="profile.id"><td data-label="档案"><strong>{{ profile.name }}</strong><small>{{ profile.industry }} · 修订 {{ profile.revision }}</small></td><td data-label="归属"><small>{{ profile.user_id }}</small></td><td data-label="状态"><span class="admin-pill">{{ profile.deleted_at ? '回收站' : labels(profile.status) }}</span><small>{{ labels(profile.stage) }}</small></td><td data-label="创建时间">{{ date(profile.created_at) }}</td><td data-label="诊断"><button class="admin-inline-link" @click="inspect(profile)">只读查看 ↗</button></td></tr></tbody></table></div>
        <div v-if="hotspots.length" class="admin-table-wrap"><table><thead><tr><th>来源</th><th>自动状态</th><th>人工状态</th><th>采集时间</th><th>管理</th></tr></thead><tbody><tr v-for="hotspot in hotspots" :key="hotspot.id"><td data-label="来源"><strong>{{ hotspot.title }}</strong><small>{{ hotspot.channel }}</small></td><td data-label="自动状态"><span class="admin-pill">{{ hotspot.expired ? '已过期' : hotspot.safe ? '筛选通过' : '未通过' }}</span></td><td data-label="人工状态"><span class="admin-pill" :class="hotspot.manually_hidden ? 'bad' : 'good'">{{ hotspot.manually_hidden ? '已下架' : '未下架' }}</span></td><td data-label="采集时间">{{ date(hotspot.fetched_at) }}</td><td data-label="管理"><button class="admin-inline-link" @click="open({ title: hotspot.manually_hidden ? '恢复来源' : '下架来源', description: '恢复后仍需满足自动筛选和时效规则。', path: `/hotspots/${hotspot.id}/visibility`, data: { hidden: !hotspot.manually_hidden, expected: hotspot.manually_hidden } })">{{ hotspot.manually_hidden ? '恢复' : '下架' }}</button></td></tr></tbody></table></div>
        <div v-if="collections.length" class="admin-table-wrap"><table><thead><tr><th>采集 / 模型</th><th>状态</th><th>调用次数</th><th>已记录 tokens</th><th>开始 / 完成</th></tr></thead><tbody><tr v-for="collection in collections" :key="collection.id"><td data-label="采集 / 模型"><strong>公共热点采集</strong><small>{{ collection.model }}<br>{{ collection.embedding_model }}<br>{{ collection.id }}</small></td><td data-label="状态"><span class="admin-pill" :class="collection.status === 'failed' ? 'bad' : collection.status === 'succeeded' ? 'good' : ''">{{ labels(collection.status) }}</span><small v-if="collection.error">{{ collection.error }}</small><small v-if="collection.diagnostics.stage">阶段：{{ collectionStages[collection.diagnostics.stage] || '未知' }}<br>候选 {{ collection.diagnostics.candidates ?? 0 }} · 通过 {{ collection.diagnostics.approved ?? 0 }} · 新增 {{ collection.diagnostics.added ?? 0 }}</small><details v-if="collection.diagnostics.sources?.length"><summary>查看来源状态</summary><p v-for="(source, index) in collection.diagnostics.sources" :key="index" class="admin-muted">{{ sourceNames[source.source] || '资讯来源' }}：{{ sourceStatuses[source.status] || '未知' }}<template v-if="source.http_status">（HTTP {{ source.http_status }}）</template><template v-if="source.items !== undefined"> · {{ source.items }} 条</template></p></details><small v-if="collection.diagnostics.embedding_fallback">向量服务不可用，已按标题去重</small></td><td data-label="调用次数">模型 {{ collection.llm_calls }} 次<small>向量 {{ collection.embedding_calls }} 次</small></td><td data-label="已记录 tokens">{{ number(collection.input_tokens) }} 入 / {{ number(collection.output_tokens) }} 出<small>向量 {{ number(collection.embedding_tokens) }}</small></td><td data-label="开始 / 完成">{{ date(collection.created_at) }}<small>{{ date(collection.finished_at) }}</small></td></tr></tbody></table></div>
        <div v-if="audits.length" class="admin-table-wrap"><table><thead><tr><th>操作 / 对象</th><th>原因 / 变更</th><th>操作人 / IP</th><th>结果 / 时间</th></tr></thead><tbody><tr v-for="audit in audits" :key="audit.id"><td data-label="操作 / 对象"><strong>{{ audit.action }}</strong><small>{{ audit.target }}</small></td><td data-label="原因 / 变更">{{ audit.reason }}<details v-if="Object.keys(audit.changes || {}).length"><summary>查看变更</summary><pre>{{ pretty(audit.changes) }}</pre></details></td><td data-label="操作人 / IP"><small>{{ audit.actor_id || '服务器 CLI' }}<br>{{ audit.ip || '—' }}</small></td><td data-label="结果 / 时间"><span class="admin-pill" :class="audit.result === 'success' ? 'good' : 'bad'">{{ labels(audit.result) }}</span><small>{{ date(audit.created_at) }}</small></td></tr></tbody></table></div>
        <div v-if="cursor" class="admin-pagination"><button class="admin-button" :disabled="loading" @click="load(true)">{{ loading ? '正在加载…' : '加载更多记录 ↓' }}</button></div>
      </section>
      <p v-if="['runs', 'hotspots'].includes(section)" class="admin-footnote">tokens 为服务返回的已记录用量；未返回用量不代表实际零费用。</p>
      <p class="admin-footnote">{{ section === 'audits' ? '审计记录保留 180 天，后台只读。' : section === 'profiles' ? '用户资料按次填写查看原因，退出或锁定后清空。' : '时间均为北京时间。' }}</p>
    </template>
    <van-popup :show="!!dialog" round position="center" class="admin-modal" :close-on-click-overlay="!submitting" @update:show="value => { if (!value && !submitting) dialog = null }">
      <form v-if="dialog" @submit.prevent="submit"><p class="admin-eyebrow">CONFIRM ACTION</p><h2>{{ dialog.title }}</h2><p class="admin-muted">{{ dialog.description }}</p><label v-if="dialog.quota" class="admin-form-label">每天 AI 次数<input v-model="quota" type="number" min="0" max="1000" step="1" placeholder="留空使用系统默认值"></label><label v-if="dialog.inspect" class="admin-form-label">资料类型<select v-model="inspectSection"><option v-for="[key, label] in inspectOptions" :key="key" :value="key">{{ label }}</option></select></label><label class="admin-form-label">操作原因<textarea v-model="reason" required minlength="5" maxlength="300" rows="3" placeholder="如：协助用户排查测算数据问题" /></label><p v-if="dialogError" role="alert" class="admin-error">{{ dialogError }}</p><div class="admin-dialog-actions"><button type="button" class="admin-button" :disabled="submitting" @click="dialog = null">取消</button><button class="admin-button primary" :disabled="submitting">{{ submitting ? '处理中…' : '确认'+(dialog.inspect ? '查看' : '操作') }}</button></div></form>
    </van-popup>
    <van-popup :show="sensitive !== null" position="right" class="admin-drawer" @update:show="value => { if (!value) closeSensitive() }"><div class="admin-drawer-head"><div><p class="admin-eyebrow">READ ONLY</p><h2>{{ selectedProfile?.name }}</h2><p class="admin-muted">{{ inspectOptions.find(i => i[0] === inspectSection)?.[1] }} · 只读资料</p></div><button aria-label="关闭资料" class="admin-button" @click="closeSensitive">关闭 ×</button></div><template v-if="sensitiveItems"><article v-for="(item, index) in sensitiveItems" :key="index" class="admin-sensitive-item"><p v-if="item.created_at" class="admin-muted">{{ date(String(item.created_at)) }}</p><template v-if="inspectSection === 'chat' || inspectSection === 'reports' || inspectSection === 'copy'"><span v-if="item.role" class="admin-pill">{{ item.role === 'user' ? '用户' : '商业罗盘' }}</span><MarkdownText :content="String(item.content || '暂无内容')" /></template><pre v-else>{{ pretty(item) }}</pre></article><p v-if="!sensitiveItems.length" class="admin-empty">暂无资料</p><button v-if="sensitiveCursor" class="admin-button" :disabled="submitting" @click="moreSensitive">加载更多</button></template><pre v-else class="admin-sensitive-pre">{{ pretty(sensitive) }}</pre></van-popup>
  </div>
</template>

<style>
.admin-page { animation: admin-enter .35s var(--ease) both; }
.admin-page-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; margin-bottom: 28px; }
.admin-page-head h1 { font-size: 30px; letter-spacing: -.03em; margin: 8px 0 10px; }
.admin-page-head>div>p:last-child { color: var(--muted); font-size: 14px; margin: 0; }
.admin-head-actions { display: flex; gap: 8px; flex-shrink: 0; }
.admin-button { border: 1px solid var(--line); background: var(--surface); border-radius: 8px; padding: 10px 16px; font: inherit; font-size: 13px; color: var(--ink); cursor: pointer; transition: border-color .2s, transform .2s, box-shadow .2s; }
.admin-button:hover { border-color: var(--accent); box-shadow: var(--shadow-card); transform: translateY(-1px); }
.admin-button.primary { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.admin-button:disabled { opacity: .5; cursor: wait; transform: none; }
.admin-page select,.admin-page input,.admin-page textarea,.admin-modal input,.admin-modal textarea,.admin-modal select { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: var(--surface); font: inherit; font-size: 13px; color: var(--ink); min-width: 0; max-width: 100%; }
.admin-page input:focus,.admin-page select:focus,.admin-modal textarea:focus,.admin-modal input:focus { outline: 2px solid var(--accent-line); outline-offset: 2px; }
.admin-stats { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 16px; margin-bottom: 24px; }
.admin-stat { padding: 24px; overflow: hidden; animation: admin-enter .5s var(--ease) both; position: relative; }
.admin-stat>div { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: var(--muted); }
.admin-stat-index { font-family: var(--font-num); color: var(--faint); }
.admin-stat .num { display: block; font-size: 48px; margin: 18px 0 10px; line-height: 1; font-family: var(--font-num); }
.admin-stat p { font-size: 11px; color: var(--muted); margin: 12px 0 0; }
.admin-stat-accent { background: var(--ink); color: var(--side-ink); border-color: var(--ink); }
.admin-stat-accent>div,.admin-stat-accent p,.admin-stat-accent .admin-stat-index { color: var(--side-muted); }
.admin-stat-accent::after { content: ''; position: absolute; width: 100px; height: 100px; border: 1px solid var(--side-line); border-radius: 50%; right: -26px; bottom: -40px; box-shadow: 0 0 0 20px var(--side-hover),0 0 0 40px var(--side-hover); pointer-events: none; }
.admin-trend { padding: 28px 28px 18px; margin-bottom: 24px; }
.admin-panel-title { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.admin-panel-title h2,.admin-panel h2,.admin-list h2 { margin: 4px 0 0; font-size: 18px; font-weight: 600; }
.admin-chart { display: flex; align-items: end; height: 230px; gap: clamp(4px,1.5vw,24px); padding-top: 30px; }
.admin-bar-column { position: relative; flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: end; }
.admin-bar { background: var(--ink); width: 100%; max-width: 72px; border-radius: 4px 4px 0 0; transform-origin: bottom; animation: admin-bar-grow .65s var(--ease) both; animation-delay: var(--delay); overflow: hidden; position: relative; transition: filter .2s; }
.admin-bar>div { position: absolute; top: 0; width: 100%; background: var(--accent); }
.admin-bar-column:hover .admin-bar { filter: brightness(1.4); }
.admin-bar-value { font-family: var(--font-num); font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.admin-bar-date { display: block; min-height: 30px; padding-top: 10px; font-size: 10px; color: var(--faint); white-space: nowrap; }
.admin-chart-tip { display: none; position: absolute; bottom: 100%; z-index: 2; background: var(--ink); color: var(--side-ink); border-radius: 6px; padding: 10px; white-space: nowrap; font-size: 12px; line-height: 1.8; pointer-events: none; }
.admin-bar-column:hover .admin-chart-tip,.admin-bar-column:focus .admin-chart-tip { display: block; }
.admin-chart-legend { display: flex; justify-content: center; align-items: center; font-size: 11px; color: var(--muted); gap: 8px; }
.admin-chart-legend i { width: 8px; height: 8px; border-radius: 2px; background: var(--ink); margin-left: 12px; }
.admin-chart-legend .failed { background: var(--accent); }
.admin-overview-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.admin-panel { padding: 28px; min-width: 0; }
.admin-rate { display: block; font-family: var(--font-num); font-size: 40px; margin-top: 16px; }
.admin-rate small { font: 12px var(--font-cn); margin-left: 10px; color: var(--muted); }
.admin-muted { color: var(--muted); font-size: 12px; line-height: 1.8; }
.admin-dl { font-size: 13px; margin: 18px 0 0; }
.admin-dl>div { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 14px 0; border-bottom: 1px solid var(--line-soft); }
.admin-dl>div:last-child { border: 0; }
.admin-dl dt { color: var(--muted); }.admin-dl dd { margin: 0; text-align: right; overflow-wrap: anywhere; }
.admin-inline-link,.admin-row-actions button { border: 0; background: none; color: var(--accent-ink); font: inherit; font-size: 12px; cursor: pointer; text-decoration: none; padding: 6px 0; display: inline-block; }
.admin-inline-link:hover,.admin-row-actions button:hover { text-decoration: underline; }
.admin-pill { font-size: 11px; line-height: 1.6; padding: 3px 8px; display: inline-flex; border-radius: 5px; color: var(--muted); background: var(--surface-2); white-space: nowrap; }
.admin-pill.good { color: var(--good); background: var(--good-soft); }.admin-pill.bad { color: var(--bad); background: var(--bad-soft); }
.admin-filters { padding: 18px; display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }
.admin-filters>input { flex: 1; min-width: 160px; }.admin-filters>label { display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--muted); }
.admin-list { overflow: hidden; }.admin-list-heading { padding: 22px 24px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line-soft); }
.admin-table-wrap { overflow-x: auto; }.admin-list table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; table-layout: fixed; }
.admin-list th { color: var(--muted); background: var(--surface-2); font-size: 11px; font-weight: 500; padding: 14px 18px; }
.admin-list td { padding: 18px; border-top: 1px solid var(--line-soft); vertical-align: top; line-height: 1.8; overflow-wrap: anywhere; }
.admin-list tr { transition: background .2s; }.admin-list tbody tr:hover { background: var(--surface-2); }
.admin-list td strong { font-weight: 550; font-size: 13px; }.admin-list td small { display: block; color: var(--muted); font-size: 10px; margin-top: 6px; line-height: 1.8; }
.admin-row-actions button { margin-right: 10px; }.admin-empty { text-align: center; padding: 60px 20px; color: var(--muted); font-size: 14px; }
.admin-pagination { text-align: center; padding: 20px; border-top: 1px solid var(--line-soft); }.admin-footnote { font-size: 11px; color: var(--faint); margin: 18px 4px; }
.admin-notice { padding: 12px 16px; background: var(--good-soft); color: var(--good); border-radius: 8px; font-size: 13px; }
.admin-modal { width: min(480px, calc(100vw - 32px)); padding: 28px; }.admin-modal h2 { font-size: 21px; margin: 10px 0; }
.admin-form-label { display: flex; flex-direction: column; gap: 10px; margin-top: 22px; font-size: 13px; }.admin-dialog-actions { margin-top: 24px; display: flex; justify-content: end; gap: 12px; }
.admin-drawer { width: min(720px,100vw); height: 100dvh; padding: 28px; background: var(--surface); }.admin-drawer-head { display: flex; justify-content: space-between; align-items: start; gap: 16px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.admin-drawer h2 { font-size: 22px; margin: 8px 0; }.admin-drawer pre,.admin-list pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; line-height: 1.9; background: var(--surface-2); padding: 16px; border-radius: 6px; }
.admin-sensitive-item { padding: 16px 0; border-bottom: 1px solid var(--line-soft); }.admin-sensitive-pre { margin-top: 24px; }
.admin-status-large { display: block; font-size: 25px; margin: 22px 0 16px; }.admin-list summary { cursor: pointer; color: var(--accent-ink); font-size: 11px; margin-top: 6px; }
@keyframes admin-bar-grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@media(max-width: 1200px) { .admin-stats { gap: 12px; }.admin-stat { padding: 20px; }.admin-stat .num { font-size: 40px; }.admin-list td,.admin-list th { padding: 14px 12px; } }
@media(max-width: 900px) { .admin-stats { grid-template-columns: repeat(2, minmax(0,1fr)); }.admin-overview-bottom { grid-template-columns: 1fr; gap: 18px; }.admin-page-head { align-items: start; }.admin-page-head h1 { font-size: 26px; }.admin-head-actions { flex-wrap: wrap; justify-content: end; }.admin-page-head .admin-eyebrow { font-size: 9px!important; } }
@media(max-width: 720px) { .admin-page-head { flex-wrap: wrap; gap: 18px; }.admin-page-head h1 { font-size: 26px; }.admin-head-actions { margin-left: auto; }.admin-stats { gap: 10px; }.admin-stat { padding: 18px 16px; }.admin-stat .num { font-size: 38px; }.admin-stat p { font-size: 10px; }.admin-trend,.admin-panel { padding: 20px; }.admin-chart { height: 200px; gap: 6px; }.admin-panel-title { align-items: start; }.admin-panel-title h2 { font-size: 17px; }.admin-panel-title .admin-pill { font-size: 9px; }.admin-bar-date { font-size: 9px; }.admin-bar-value { font-size: 10px; }.admin-filters { padding: 14px; gap: 8px; }.admin-filters>input { min-width: 100%; }.admin-filters select { flex: 1; }.admin-filters>.admin-button { margin-left: auto; }.admin-list-heading { padding: 18px; }.admin-list table,.admin-list tbody,.admin-list tr,.admin-list td { display: block; width: 100%; }.admin-list thead { display: none; }.admin-list tr { padding: 16px; border-top: 1px solid var(--line); }.admin-list tr:first-child { border-top: 0; }.admin-list td { padding: 6px 0; border: 0; }.admin-list td::before { content: attr(data-label); display: block; color: var(--faint); font-size: 10px; margin-bottom: 3px; }.admin-list td small { font-size: 11px; margin: 3px 0; }.admin-list .admin-row-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }.admin-list .admin-row-actions::before { display: none; }.admin-row-actions button { margin: 0; }.admin-drawer { padding: 22px 16px; }.admin-modal { padding: 24px; } }
</style>
