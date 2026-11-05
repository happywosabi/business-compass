<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  profilesApi,
  parameterAt,
  type Field,
  type Parameter,
  type Profile,
  type Template,
} from '@/api/profiles'
import { ApiError, errorMessage } from '@/api/client'
import { emptyValue, type JsonSchema } from '@/utils/parameters'
import { useBreakpoint } from '@/composables/useBreakpoint'
import SchemaInput from './SchemaInput.vue'

const props = defineProps<{
  field: Field
  profile: Profile
  template: Template
  anchor?: DOMRect
}>()
const emit = defineEmits<{ close: []; saved: [profile: Profile]; refreshed: [profile: Profile] }>()
const { isDesktop } = useBreakpoint()
const original = parameterAt(props.profile, props.field.key)
const draft = ref<Parameter>(
  original
    ? JSON.parse(JSON.stringify(original))
    : {
        base: emptyValue(props.field.value_schema as JsonSchema, props.template.definitions),
        source: 'user',
      },
)
const saving = ref(false),
  error = ref(''),
  conflicted = ref(false),
  revision = ref(props.profile.revision)
const panel = ref<HTMLElement>()
const tiered = ref(Boolean(original?.pessimistic != null || original?.optimistic != null))
const numeric = computed(() =>
  ['number', 'integer'].includes(String(props.field.value_schema.type)),
)
const position = computed(() => {
  if (!isDesktop.value || !props.anchor) return {}
  return {
    left: `${Math.min(Math.max(props.anchor.left, 90), window.innerWidth - 452)}px`,
    top: `${Math.min(Math.max(props.anchor.top - 70, 24), Math.max(24, window.innerHeight - 660))}px`,
  }
})
function failed(e: unknown) {
  error.value = errorMessage(e)
  conflicted.value = e instanceof ApiError && e.status === 409
}
async function save(clear = false) {
  saving.value = true
  error.value = ''
  try {
    const value = clear
      ? null
      : {
          ...draft.value,
          source: 'user',
          pessimistic:
            tiered.value && draft.value.pessimistic !== '' ? draft.value.pessimistic : null,
          optimistic: tiered.value && draft.value.optimistic !== '' ? draft.value.optimistic : null,
        }
    emit(
      'saved',
      await profilesApi.parameters(props.profile.id, revision.value, { [props.field.key]: value }),
    )
  } catch (e) {
    failed(e)
  } finally {
    saving.value = false
  }
}
async function refresh() {
  try {
    const latest = await profilesApi.get(props.profile.id)
    revision.value = latest.revision
    emit('refreshed', latest)
    conflicted.value = false
    error.value = '已取得最新档案。你的输入已保留，请确认后再保存。'
  } catch (e) {
    failed(e)
  }
}
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape' && !saving.value) emit('close')
  if (event.key === 'Tab' && panel.value) {
    const elements = Array.from(
      panel.value.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, textarea'),
    )
    const first = elements[0],
      last = elements.at(-1)
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }
}
let previousFocus: HTMLElement | null = null
let previousOverflow = ''
onMounted(async () => {
  previousFocus = document.activeElement as HTMLElement
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', keyboard)
  await nextTick()
  panel.value?.focus()
})
onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
  document.removeEventListener('keydown', keyboard)
  previousFocus?.focus()
})
</script>
<template>
  <Teleport to="body"
    ><div class="editor-layer" @click.self="!saving && emit('close')">
      <section
        ref="panel"
        class="param-editor bc-card"
        :style="position"
        tabindex="-1"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-title"
      >
        <header class="editor-heading">
          <div>
            <span class="eyebrow">调整一个假设</span>
            <h2 id="editor-title">
              {{ field.label }}<small v-if="field.unit"> / {{ field.unit }}</small>
            </h2>
          </div>
          <button class="close-button" aria-label="关闭" :disabled="saving" @click="emit('close')">
            ×
          </button>
        </header>
        <p class="sub">{{ field.ask ?? '不确定时可以先保留默认值，之后再来调整。' }}</p>
        <form class="form-stack" @submit.prevent="save()">
          <div class="input-label">
            <span>{{ numeric ? '一般情况下' : field.label }}</span
            ><SchemaInput
              v-model="draft.base"
              :schema="field.value_schema as JsonSchema"
              :definitions="template.definitions"
              :label="field.label"
            />
          </div>
          <template v-if="numeric"
            ><label class="range-toggle"
              ><input v-model="tiered" type="checkbox" /> 再填一个范围，看看好坏情况</label
            ><Transition name="expand"
              ><div v-if="tiered" class="tier-inputs">
                <label class="input-label"
                  ><span>差的时候</span
                  ><input
                    v-model.number="draft.pessimistic"
                    type="number"
                    class="bc-input num"
                    step="any"
                    placeholder="留空等于一般情况" /></label
                ><label class="input-label"
                  ><span>好的时候</span
                  ><input
                    v-model.number="draft.optimistic"
                    type="number"
                    class="bc-input num"
                    step="any"
                    placeholder="留空等于一般情况"
                /></label>
                <p class="sub">收入类：差的时候较低；成本类：差的时候较高。</p>
              </div></Transition
            ></template
          >
          <label class="input-label"
            ><span>这个数字的依据（选填）</span
            ><textarea
              v-model="draft.note"
              class="bc-input"
              rows="2"
              maxlength="1000"
              placeholder="比如：房东报价、供应商报价，或自己的估计"
            />
          </label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button v-if="conflicted" type="button" class="text-link" @click="refresh">
            刷新档案，保留我的输入
          </button>
          <div class="editor-actions">
            <button
              v-if="original"
              type="button"
              class="text-link"
              :disabled="saving"
              @click="save(true)"
            >
              清空</button
            ><van-button
              type="primary"
              native-type="submit"
              :loading="saving"
              :disabled="conflicted"
              >保存这个数字</van-button
            >
          </div>
        </form>
      </section>
    </div></Teleport
  >
</template>
<style scoped>
.editor-layer {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(16, 38, 61, 0.28);
  backdrop-filter: blur(4px);
  animation: veil-in 0.2s;
}
.param-editor {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  border-radius: 20px 20px 0 0;
  max-height: 90dvh;
  overflow-y: auto;
  padding: 24px 20px max(24px, env(safe-area-inset-bottom));
  animation: sheet-in 0.35s var(--spring);
  box-shadow: var(--shadow-pop);
}
.editor-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.editor-heading small {
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
}
.tier-inputs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.tier-inputs p {
  grid-column: 1/-1;
}
.range-toggle {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--accent-ink);
}
.editor-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 24px;
}
.expand-enter-active,
.expand-leave-active {
  transition:
    opacity 0.2s,
    transform 0.2s;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
@media (min-width: 768px) {
  .param-editor {
    width: 428px;
    left: 50%;
    top: 10vh;
    bottom: auto;
    right: auto;
    max-height: 84vh;
    border-radius: 14px;
    padding: 24px;
    animation: pop-in 0.25s var(--spring);
  }
}
@keyframes sheet-in {
  from {
    transform: translateY(100%);
  }
}
@keyframes pop-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.97);
  }
}
@keyframes veil-in {
  from {
    background: transparent;
    backdrop-filter: blur(0);
  }
}
</style>
