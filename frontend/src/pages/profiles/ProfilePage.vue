<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import {
  profilesApi,
  parameterAt,
  type Change,
  type Field,
  type Profile,
  type Template,
} from '@/api/profiles'
import { evaluationsApi } from '@/api/evaluations'
import { errorMessage } from '@/api/client'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import OrchardForm from '@/components/OrchardForm.vue'
import type { OrchardParams } from '@/api/orchard'
import ParamRow from '@/components/ParamRow.vue'
import ParamEditor from '@/components/ParamEditor.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import { PROFILE_STAGES, STAGES, displayValue } from '@/utils/parameters'

const route = useRoute(),
  router = useRouter()
const profile = ref<Profile>(),
  template = ref<Template>(),
  loading = ref(true),
  error = ref(''),
  busy = ref(false)
const editing = ref<Field>(),
  anchor = ref<DOMRect>(),
  savedKey = ref(''),
  changes = ref<Change[]>([]),
  showHistory = ref(false)
const info = ref(false),
  infoName = ref(''),
  infoCity = ref(''),
  infoStage = ref<'idea' | 'preparing' | 'operating'>('idea')
const groups = computed(() =>
  Object.entries(
    template.value?.groups && Object.keys(template.value.groups).length
      ? template.value.groups
      : STAGES,
  )
    .map(([key, label]) => ({
      key,
      label,
      fields: template.value?.fields.filter((f) => f.stage === key) ?? [],
    }))
    .filter((g) => g.fields.length),
)
const total = computed(() => template.value?.quick_required_keys?.length ?? 0)
const progress = computed(() => total.value - (profile.value?.quick_missing.length ?? total.value))
async function saveOrchard(changes: Record<string, unknown>) {
  await action(async () => {
    profile.value = await profilesApi.parameters(
      profile.value!.id,
      profile.value!.revision,
      changes,
    )
    showToast('果园档案已保存')
  })
}
let flash: ReturnType<typeof setTimeout>
async function load() {
  loading.value = true
  error.value = ''
  editing.value = undefined
  try {
    const [p, t] = await Promise.all([
      profilesApi.get(String(route.params.id)),
      profilesApi.templates(),
    ])
    profile.value = p
    template.value = t.find((item) => item.key === p.template_key)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
function edit(field: Field, event: MouseEvent) {
  editing.value = field
  anchor.value = (event.currentTarget as HTMLElement).getBoundingClientRect()
}
function saved(next: Profile) {
  savedKey.value = editing.value?.key ?? ''
  profile.value = next
  editing.value = undefined
  clearTimeout(flash)
  flash = setTimeout(() => (savedKey.value = ''), 1600)
  showToast('已记下这个数字')
}
async function action(task: () => Promise<void>) {
  busy.value = true
  error.value = ''
  try {
    await task()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function evaluate() {
  await action(async () => {
    const result = await evaluationsApi.create(profile.value!.id, profile.value!.revision)
    await router.push(`/profiles/${profile.value!.id}/results/${result.id}`)
  })
}
async function remove() {
  try {
    await showConfirmDialog({
      title: '把这份档案暂时收起来？',
      message: '删除后 30 天内，可以在“最近删除”中恢复。',
      confirmButtonText: '删除档案',
    })
  } catch {
    return
  }
  await action(async () => {
    await profilesApi.remove(profile.value!.id, profile.value!.revision)
    await router.push('/')
  })
}
async function copy() {
  await action(async () => {
    const next = await profilesApi.copy(profile.value!.id, profile.value!.revision)
    await router.push(`/profiles/${next.id}`)
  })
}
async function archive() {
  await action(async () => {
    profile.value = await profilesApi.update(profile.value!.id, {
      revision: profile.value!.revision,
      status: profile.value!.status === 'archived' ? 'draft' : 'archived',
    })
    showToast('档案已更新')
  })
}
async function history() {
  showHistory.value = !showHistory.value
  if (showHistory.value)
    await action(async () => {
      changes.value = await profilesApi.changes(profile.value!.id)
    })
}
function editInfo() {
  infoName.value = profile.value!.name
  infoCity.value = profile.value!.city
  infoStage.value = profile.value!.stage
  info.value = !info.value
}
async function saveInfo() {
  await action(async () => {
    profile.value = await profilesApi.update(profile.value!.id, {
      revision: profile.value!.revision,
      name: infoName.value,
      city: infoCity.value,
      stage: infoStage.value,
    })
    info.value = false
  })
}
async function recalculateDefault(key: string) {
  try {
    await showConfirmDialog({
      title: '重新估算这个默认值？',
      message: '会按现在的客单价重新估算按单成本，并记录这次修改。',
    })
  } catch {
    return
  }
  await action(async () => {
    profile.value = await profilesApi.defaults(profile.value!.id, profile.value!.revision, [key])
    showToast('默认值已重新估算')
  })
}
watch(() => route.params.id, load)
onMounted(load)
onScopeDispose(() => clearTimeout(flash))
</script>
<template>
  <div class="page profile-page">
    <PageHead :title="profile?.name ?? '商业档案'" back="/" back-label="我的档案"
      ><template v-if="profile" #actions
        ><button class="text-link" :disabled="busy" @click="copy">复制方案 ↗</button></template
      ></PageHead
    >
    <p v-if="error" class="form-error" role="alert">
      {{ error }}<button class="text-link" @click="load">刷新档案</button>
    </p>
    <div v-if="loading" class="bc-card"><div class="skeleton" style="height: 150px" /></div>
    <template v-else-if="profile && template">
      <section class="profile-overview">
        <div class="overview-label">
          <span class="eyebrow">你的开店航线</span>
          <p>{{ profile.city }} · {{ template.label }} · {{ PROFILE_STAGES[profile.stage] }}</p>
          <button class="text-link" @click="editInfo">修改基本信息</button>
        </div>
        <div class="overview-progress">
          <div>
            <span>快速测算准备度</span
            ><b
              ><AnimatedNumber :value="progress" /> <small>/ {{ total }}</small></b
            >
          </div>
          <div class="progress-track"><i :style="{ width: `${(progress / total) * 100}%` }" /></div>
          <p>
            {{
              profile.quick_missing.length
                ? `再补 ${profile.quick_missing.length} 个数字，就能看第一版结果。`
                : '关键数字已齐，随时可以先算一下。'
            }}
          </p>
        </div>
        <CompassMark :size="75" motion="settle" />
      </section>
      <Transition name="expand"
        ><form v-if="info" class="bc-card info-form" @submit.prevent="saveInfo">
          <label class="input-label"
            >档案名称<input v-model="infoName" class="bc-input" required maxlength="80" /></label
          ><label class="input-label"
            >城市<input v-model="infoCity" class="bc-input" required maxlength="60" /></label
          ><label class="input-label"
            >阶段<select v-model="infoStage" class="bc-input">
              <option
                v-for="(label, key) in profile.template_key === 'orchard'
                  ? { operating: '经营中' }
                  : PROFILE_STAGES"
                :key="key"
                :value="key"
              >
                {{ label }}
              </option>
            </select></label
          ><van-button native-type="submit" type="primary" :loading="busy">保存信息</van-button>
        </form></Transition
      >
      <div class="profile-workspace">
        <OrchardForm
          v-if="profile.template_key === 'orchard'"
          :key="profile.revision"
          :parameters="profile.parameters as OrchardParams"
          :busy="busy"
          @submit="saveOrchard"
        />
        <div v-else class="parameter-groups">
          <section
            v-for="(group, i) in groups"
            :id="`group-${group.key}`"
            :key="group.key"
            class="bc-card parameter-group"
            :style="{ '--order': i }"
          >
            <header class="group-heading">
              <div class="group-title">
                <span class="group-index num">0{{ i + 1 }}</span>
                <h2>{{ group.label }}</h2>
              </div>
              <span class="sub"
                >{{ group.fields.filter((f) => parameterAt(profile!, f.key)).length }} /
                {{ group.fields.length }}</span
              >
            </header>
            <div>
              <ParamRow
                v-for="field in group.fields"
                :key="field.key"
                :field="field"
                :value="parameterAt(profile, field.key)"
                :saved="savedKey === field.key"
                @edit="edit(field, $event)"
              />
            </div>
          </section>
        </div>
        <aside class="profile-aside">
          <section class="bc-card next-step">
            <span class="eyebrow">下一步 / 看清可能性</span><CompassMark :size="80" />
            <h2>{{ progress === total ? '数字齐了，看看结果' : '把关键数字先填好' }}</h2>
            <p class="sub">
              {{
                progress === total
                  ? profile.template_key === 'orchard'
                    ? '产销与成本已确认，可以核算本期结余。'
                    : '其余缺项会用默认值补齐，并明确告诉你哪些是假设。'
                  : '不用一次填完。拿不准的先留着，问过房东、看过报价再回来。'
              }}
            </p>
            <div class="required-list">
              <a
                v-for="key in profile.quick_missing"
                :key="key"
                :href="`#group-${template.fields.find((f) => f.key === key)?.stage}`"
                ><span class="required-dot" />{{ template.fields.find((f) => f.key === key)?.label
                }}<span>↗</span></a
              >
            </div>
            <van-button
              type="primary"
              :disabled="progress !== total"
              :loading="busy"
              @click="evaluate"
              >先算一下 ↗</van-button
            ><router-link class="text-link" :to="`/profiles/${profile.id}/results`"
              >查看历史测算</router-link
            >
            <router-link class="text-link" :to="`/profiles/${profile.id}/interview`"
              >和 AI 聊聊，帮我填写 ↗</router-link
            >
            <p class="sub">所有修改自动留痕，只有你能查看。</p>
          </section>
          <section v-if="profile.derived_stale_keys.length" class="bc-card stale-card">
            <h2>一个数字可能要跟着调整</h2>
            <p class="sub">
              客单价变了，按原客单价估的成本仍保留着。你可以重新估算，或者自己填写报价。
            </p>
            <button
              v-for="key in profile.derived_stale_keys"
              :key="key"
              class="text-link"
              :disabled="busy"
              @click="recalculateDefault(key)"
            >
              重新估算按单成本 ↗
            </button>
          </section>
          <section class="bc-card side-guide">
            <span class="eyebrow">一眼找到</span
            ><a v-for="group in groups" :key="group.key" :href="`#group-${group.key}`"
              >{{ group.label }} <span>↓</span></a
            >
          </section>
        </aside>
      </div>
      <section class="bc-card profile-tools">
        <button class="text-link" :disabled="busy" @click="history">
          {{ showHistory ? '收起' : '查看' }}数字修改记录</button
        ><button class="text-link" :disabled="busy" @click="archive">
          {{ profile.status === 'archived' ? '移回进行中' : '归档这个想法' }}</button
        ><button class="text-link delete-link" :disabled="busy" @click="remove">删除档案</button>
      </section>
      <section v-if="showHistory" class="bc-card">
        <h2>每个数字，都有来路</h2>
        <p v-if="!changes.length" class="sub">还没有参数修改记录。</p>
        <ol class="change-list">
          <li v-for="item in changes" :key="item.id">
            <span class="history-dot" />
            <div>
              <b>{{ template.fields.find((f) => f.key === item.parameter_key)?.label }}</b>
              <p>
                {{ displayValue(item.old_value?.base, undefined, item.parameter_key) }} →
                {{ displayValue(item.new_value?.base, undefined, item.parameter_key) }}
              </p>
              <small class="sub"
                >第 {{ item.profile_revision }} 次修改 · {{ item.reason ?? '手工修改' }}</small
              >
            </div>
          </li>
        </ol>
      </section>
      <ParamEditor
        v-if="editing"
        :key="editing.key"
        :field="editing"
        :profile="profile"
        :template="template"
        :anchor="anchor"
        @close="editing = undefined"
        @saved="saved"
        @refreshed="profile = $event"
      />
    </template>
  </div>
</template>
<style scoped>
.profile-overview {
  display: flex;
  align-items: center;
  gap: 28px;
  flex-wrap: wrap;
  background: linear-gradient(120deg, var(--surface), var(--accent-soft));
  border: 1px solid var(--accent-line);
  border-radius: 12px;
  padding: 24px;
  animation: compass-rise 0.5s var(--ease);
}
.overview-label {
  flex: 1;
  min-width: 180px;
}
.overview-label p {
  font-size: 14px;
  margin: 7px 0;
}
.overview-label button {
  font-size: 12px;
  color: var(--muted);
}
.overview-progress {
  width: 260px;
  max-width: 100%;
}
.overview-progress > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}
.overview-progress b {
  font-size: 26px;
  font-family: var(--font-num);
  font-weight: 600;
}
.overview-progress small {
  font-size: 14px;
  color: var(--faint);
}
.overview-progress p {
  color: var(--muted);
  font-size: 11px;
  margin-top: 7px;
}
.progress-track {
  height: 5px;
  background: var(--line-soft);
  border-radius: 10px;
  overflow: hidden;
}
.progress-track i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.7s var(--ease);
}
.profile-workspace {
  display: grid;
  gap: 20px;
}
.parameter-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.parameter-group {
  gap: 8px;
  scroll-margin-top: 20px;
  animation: compass-rise 0.5s calc(var(--order) * 70ms) var(--ease) both;
}
.group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.group-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.group-index {
  color: var(--accent);
  font-size: 23px;
}
.group-title h2 {
  font-size: 17px;
}
.profile-aside {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-self: start;
}
.next-step > svg {
  align-self: center;
}
.required-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.required-list a {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  text-decoration: none;
  font-size: 13px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line-soft);
}
.required-list a > span:last-child {
  margin-left: auto;
  color: var(--faint);
}
.required-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
}
.side-guide {
  display: none;
}
.side-guide a {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  text-decoration: none;
  color: var(--muted);
}
.stale-card {
  background: var(--warn-soft);
  border-color: var(--accent-line);
}
.stale-card h2 {
  font-size: 15px;
}
.profile-tools {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 20px;
  font-size: 13px;
}
.delete-link {
  margin-left: auto;
  color: var(--muted);
}
.info-form {
  display: grid;
  gap: 14px;
}
.info-form button {
  align-self: end;
}
.change-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.change-list li {
  display: flex;
  gap: 14px;
  font-size: 13px;
}
.change-list b {
  font-size: 14px;
}
.change-list p {
  color: var(--muted);
}
.history-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  margin-top: 8px;
  flex: none;
}
@media (min-width: 1024px) {
  .profile-workspace {
    grid-template-columns: minmax(0, 1fr) 290px;
    align-items: start;
    gap: 24px;
  }
  .profile-aside {
    position: sticky;
    top: 24px;
  }
  .side-guide {
    display: flex;
  }
  .info-form {
    grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  }
}
@media (max-width: 767px) {
  .profile-overview {
    gap: 16px;
    padding: 20px;
  }
  .overview-progress {
    width: 100%;
  }
  .profile-overview > svg {
    display: none;
  }
  .profile-aside {
    order: -1;
  }
  .next-step {
    display: none;
  }
  .profile-tools {
    font-size: 12px;
  }
  .profile-tools .delete-link {
    margin-left: 0;
  }
}
</style>
