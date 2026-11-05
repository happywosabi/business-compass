<script setup lang="ts">
/**
 * 登录和注册（/login、/register 共用这个页面，切换时不重新加载）。
 * 桌面：左边深海蓝底介绍产品，右边表单；手机：介绍缩成顶部一小块，表单在下面。
 * 注册成功后直接登录，进入应用；验证邮箱的提示在应用顶部。
 */
import { showToast, type FieldRule, type FormInstance } from 'vant'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import CompassMark from '@/components/CompassMark.vue'
import PasswordField from '@/components/PasswordField.vue'
import { INTRO_STEPS } from '@/content/intro'
import { useAuthStore } from '@/stores/auth'
import { safeRedirect } from '@/utils/redirect'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const mode = computed<'login' | 'register'>(() => (route.name === 'register' ? 'register' : 'login'))
const isRegister = computed(() => mode.value === 'register')

const form = reactive({
  email: typeof route.query.email === 'string' ? route.query.email : '',
  password: '',
  agree: false,
})
const submitting = ref(false)
const error = ref('')
const formRef = ref<FormInstance>()

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const emailRules: FieldRule[] = [
  { required: true, message: '请填写邮箱' },
  { pattern: EMAIL_PATTERN, message: '邮箱格式不对，请检查一下' },
]
const passwordRules = computed<FieldRule[]>(() =>
  isRegister.value
    ? [
        { required: true, message: '请设置密码' },
        { validator: (value: string) => value.length >= 8, message: '密码至少需要 8 位' },
      ]
    : [{ required: true, message: '请填写密码' }],
)

watch(mode, () => {
  error.value = ''
  form.password = ''
  formRef.value?.resetValidation()
})

function switchMode(target: 'login' | 'register') {
  if (target !== mode.value) void router.replace({ name: target, query: route.query })
}

async function onSubmit() {
  error.value = ''
  if (isRegister.value && !form.agree) {
    error.value = '请先阅读并勾选同意《用户协议》和《隐私政策》'
    return
  }
  const email = form.email.trim()
  submitting.value = true
  try {
    if (isRegister.value) {
      await authApi.register({ email, password: form.password })
      try {
        await auth.login(email, form.password)
      } catch {
        // 账号已经建好，只是自动登录没成功（比如网络抖动），让用户手动登录
        showToast('注册成功，请登录')
        await router.replace({ name: 'login', query: { ...route.query, email } })
        return
      }
      showToast({ message: '注册成功！验证邮件已发到你的邮箱', duration: 3000 })
    } else {
      await auth.login(email, form.password)
    }
    await router.replace(safeRedirect(route.query.redirect))
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth">
    <section class="hero" aria-label="商业罗盘介绍">
      <CompassMark class="hero-compass" :size="150" dark motion="settle" hover-sway />
      <h1><span class="nowrap">开店之前，</span><span class="nowrap">先把账算清楚</span></h1>
      <p class="lede">说说你想开什么店。商业罗盘帮你算出要准备多少钱、第几个月收回投入，还有最怕什么。</p>
      <ol class="steps">
        <li v-for="(step, i) in INTRO_STEPS" :key="step.title">
          <span class="n num">{{ i + 1 }}</span>
          <div>
            <b>{{ step.title }}</b>
            <span>{{ step.text }}</span>
          </div>
        </li>
      </ol>
    </section>

    <section class="panel">
      <van-form ref="formRef" class="auth-form" :show-error-message="true" @submit="onSubmit">
        <div class="tabs" role="tablist" :data-mode="mode">
          <span class="thumb" aria-hidden="true" />
          <button type="button" role="tab" :aria-selected="!isRegister" @click="switchMode('login')">登录</button>
          <button type="button" role="tab" :aria-selected="isRegister" @click="switchMode('register')">注册</button>
        </div>

        <h2 class="form-title">{{ isRegister ? '注册新账号' : '欢迎回来' }}</h2>

        <van-field
          v-model="form.email"
          class="bc-field"
          label-align="top"
          label="邮箱"
          name="email"
          type="email"
          inputmode="email"
          autocomplete="email"
          autocapitalize="off"
          :spellcheck="false"
          placeholder="你常用的邮箱"
          :rules="emailRules"
        />
        <PasswordField
          v-model="form.password"
          label="密码"
          name="password"
          :autocomplete="isRegister ? 'new-password' : 'current-password'"
          :placeholder="isRegister ? '至少 8 位，别用 12345678 这类常见密码' : ''"
          :rules="passwordRules"
        />

        <Transition name="reveal">
          <van-checkbox v-if="isRegister" v-model="form.agree" class="agree" shape="square" icon-size="18px">
            我已阅读并同意
            <RouterLink to="/terms" target="_blank" @click.stop>《用户协议》</RouterLink>和
            <RouterLink to="/privacy" target="_blank" @click.stop>《隐私政策》</RouterLink>
          </van-checkbox>
        </Transition>

        <Transition name="reveal">
          <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="16" />{{ error }}</p>
        </Transition>

        <van-button
          block
          type="primary"
          native-type="submit"
          :loading="submitting"
          :loading-text="isRegister ? '正在注册…' : '正在登录…'"
        >
          {{ isRegister ? '注册' : '登录' }}
        </van-button>

        <p v-if="!isRegister" class="foot">
          <RouterLink class="text-link" :to="{ name: 'reset-password', query: form.email ? { email: form.email.trim() } : {} }">
            忘记密码？
          </RouterLink>
        </p>
        <p v-else class="form-hint">注册后会收到一封验证邮件。验证邮箱后才能使用 AI 功能。</p>
      </van-form>
    </section>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
}

/* ---- 介绍区 ---- */
.hero {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: max(28px, env(safe-area-inset-top, 0px)) max(20px, env(safe-area-inset-right, 0px)) 40px
    max(20px, env(safe-area-inset-left, 0px));
  background-color: var(--side);
  background-image:
    linear-gradient(var(--side-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--side-grid) 1px, transparent 1px);
  background-size: 32px 32px;
  color: var(--side-ink);
}
.hero-compass {
  width: 64px;
  height: 64px;
}
.hero h1 {
  font-size: 24px;
}
.nowrap {
  display: inline-block;
}
.lede {
  font-size: 15px;
  color: var(--side-muted);
  max-width: 34em;
}
.steps {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
  flex-direction: column;
  gap: 14px;
  max-width: 34em;
}
.steps li {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  align-items: baseline;
}
.steps .n {
  font-weight: 600;
  font-size: 22px;
  line-height: 1;
  color: #c99a52;
}
.steps b {
  display: block;
  font-size: 16px;
}
.steps span:not(.n) {
  color: var(--side-muted);
  font-size: 14px;
}
/* 打开页面时，介绍内容依次上浮出现 */
.hero > * {
  animation: rise 0.5s var(--ease) both;
}
.hero > :nth-child(2) {
  animation-delay: 0.08s;
}
.hero > :nth-child(3) {
  animation-delay: 0.16s;
}
.hero > :nth-child(4) {
  animation-delay: 0.24s;
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
}

/* ---- 表单区 ---- */
.panel {
  flex: 1;
  display: flex;
  justify-content: center;
  margin-top: -16px;
  padding: 28px max(20px, env(safe-area-inset-right, 0px)) max(32px, env(safe-area-inset-bottom, 0px))
    max(20px, env(safe-area-inset-left, 0px));
  border-radius: 16px 16px 0 0;
  background: var(--surface);
}
.auth-form {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.form-title {
  font-size: 22px;
}
.tabs {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 4px;
  border-radius: 10px;
  background: var(--surface-2);
}
.tabs button {
  position: relative;
  z-index: 1;
  padding: 9px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  font-size: 15px;
  cursor: pointer;
  transition: color 0.2s;
}
.tabs button[aria-selected='true'] {
  color: var(--ink);
  font-weight: 600;
}
/* 选中标签的白色底块，切换时滑过去 */
.thumb {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 4px;
  width: calc(50% - 4px);
  border-radius: 7px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(16, 38, 61, 0.14);
  transition: transform 0.28s var(--ease);
}
.tabs[data-mode='register'] .thumb {
  transform: translateX(100%);
}
.agree {
  align-items: flex-start;
  font-size: 14px;
  line-height: 1.6;
}
.agree :deep(.van-checkbox__icon) {
  margin-top: 2px;
}
.agree :deep(.van-checkbox__label) {
  color: var(--muted);
}
.agree a {
  color: var(--ink);
  font-weight: 600;
  text-decoration: none;
}
.agree a:hover {
  text-decoration: underline;
}
.foot {
  text-align: center;
  font-size: 14px;
}

.reveal-enter-active,
.reveal-leave-active {
  transition:
    opacity 0.2s var(--ease),
    transform 0.2s var(--ease);
}
.reveal-enter-from,
.reveal-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ---- 宽屏：左右两栏 ---- */
@media (min-width: 768px) {
  .hero {
    padding: 48px 48px 56px;
  }
  .hero-compass {
    width: 96px;
    height: 96px;
  }
  .hero h1 {
    font-size: 32px;
  }
  .lede {
    font-size: 17px;
  }
  .steps {
    display: flex;
  }
  .panel {
    margin-top: 0;
    border-radius: 0;
    padding: 48px 32px;
  }
}
@media (min-width: 1024px) {
  .auth {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(420px, 0.9fr);
  }
  .hero {
    justify-content: center;
    gap: 28px;
    padding: 56px clamp(40px, 6vw, 88px);
  }
  .hero-compass {
    width: 150px;
    height: 150px;
  }
  .hero h1 {
    font-size: clamp(32px, 3.2vw, 42px);
    line-height: 1.25;
  }
  .panel {
    align-items: center;
  }
}
</style>
