<script setup lang="ts">
/**
 * 重置密码：
 * - 没有令牌：填邮箱，申请重置邮件
 * - 从邮件链接打开（/reset-password?token=...）：设置新密码
 */
import type { FieldRule } from 'vant'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import AuthFrame from '@/components/AuthFrame.vue'
import PasswordField from '@/components/PasswordField.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const form = reactive({
  email: typeof route.query.email === 'string' ? route.query.email : (auth.user?.email ?? ''),
  password: '',
})
const step = ref<'form' | 'sent' | 'done'>('form')
const sentMessage = ref('')
const submitting = ref(false)
const error = ref('')
/** 链接失效时，引导用户重新申请 */
const linkInvalid = ref(false)

// 从「重新申请」回到填邮箱时，清掉上一步的错误
watch(token, () => {
  error.value = ''
  linkInvalid.value = false
  step.value = 'form'
})

const emailRules: FieldRule[] = [
  { required: true, message: '请填写邮箱' },
  { pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: '邮箱格式不对，请检查一下' },
]
const passwordRules: FieldRule[] = [
  { required: true, message: '请设置新密码' },
  { validator: (value: string) => value.length >= 8, message: '密码至少需要 8 位' },
]

async function requestEmail() {
  error.value = ''
  submitting.value = true
  try {
    sentMessage.value = (await authApi.forgotPassword(form.email.trim())).message
    step.value = 'sent'
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}

async function setPassword() {
  error.value = ''
  linkInvalid.value = false
  submitting.value = true
  try {
    await authApi.resetPassword({ token: token.value, new_password: form.password })
    // 重置后所有设备都已退出登录
    auth.clear()
    step.value = 'done'
  } catch (e) {
    error.value = errorMessage(e)
    linkInvalid.value = error.value.includes('链接')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthFrame>
    <section class="bc-card">
      <Transition name="swap" mode="out-in">
        <!-- 申请重置邮件 -->
        <van-form v-if="!token && step === 'form'" key="request" class="form-stack" @submit="requestEmail">
          <h1>重置密码</h1>
          <p class="form-hint">填写注册时用的邮箱，我们会发一封重置密码的邮件。</p>
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
            :rules="emailRules"
          />
          <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="16" />{{ error }}</p>
          <van-button block type="primary" native-type="submit" :loading="submitting" loading-text="正在发送…">
            发送重置邮件
          </van-button>
          <p class="center"><RouterLink class="text-link" to="/login">想起来了，返回登录</RouterLink></p>
        </van-form>

        <!-- 已发送 -->
        <div v-else-if="!token && step === 'sent'" key="sent" class="state">
          <span class="badge"><AppIcon name="mail" :size="32" /></span>
          <h1>请查收邮件</h1>
          <p>{{ sentMessage }}</p>
          <p class="sub">邮件里的链接 1 小时内有效。没收到的话，看看垃圾邮件箱，或者过一分钟再发一次。</p>
          <van-button block @click="step = 'form'">再发一次</van-button>
          <van-button block type="primary" to="/login">返回登录</van-button>
        </div>

        <!-- 设置新密码 -->
        <van-form v-else-if="token && step === 'form'" key="reset" class="form-stack" @submit="setPassword">
          <h1>设置新密码</h1>
          <p class="form-hint">设置成功后，所有已登录的设备都会退出登录。</p>
          <PasswordField
            v-model="form.password"
            label="新密码"
            name="new_password"
            autocomplete="new-password"
            placeholder="至少 8 位"
            :rules="passwordRules"
          />
          <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="16" />{{ error }}</p>
          <van-button block type="primary" native-type="submit" :loading="submitting" loading-text="正在保存…">
            保存新密码
          </van-button>
          <p v-if="linkInvalid" class="center">
            <RouterLink class="text-link" :to="{ name: 'reset-password' }">重新申请重置邮件</RouterLink>
          </p>
        </van-form>

        <!-- 完成 -->
        <div v-else key="done" class="state">
          <span class="badge ok"><AppIcon name="check" :size="34" /></span>
          <h1>密码已重置</h1>
          <p class="sub">请用新密码登录。</p>
          <van-button block type="primary" to="/login">去登录</van-button>
        </div>
      </Transition>
    </section>
  </AuthFrame>
</template>

<style scoped>
.center {
  text-align: center;
  font-size: 14px;
}
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-block: 12px 4px;
  text-align: center;
}
.state .van-button + .van-button {
  margin-top: -2px;
}
.badge {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent-ink);
  animation: pop 0.45s var(--spring) both;
}
.badge.ok {
  background: var(--good-soft);
  color: var(--good);
}
@keyframes pop {
  from {
    transform: scale(0.4);
    opacity: 0;
  }
}
.swap-enter-active,
.swap-leave-active {
  transition:
    opacity 0.2s var(--ease),
    transform 0.2s var(--ease);
}
.swap-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.swap-leave-to {
  opacity: 0;
}
</style>
