<script setup lang="ts">
/** 从验证邮件的链接打开：/verify-email?token=... ，打开后自动验证 */
import { showToast } from 'vant'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import AuthFrame from '@/components/AuthFrame.vue'
import CompassMark from '@/components/CompassMark.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const state = ref<'checking' | 'ok' | 'error'>('checking')
const message = ref('')
const resending = ref(false)

onMounted(async () => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (!token) {
    state.value = 'error'
    message.value = '链接不完整，请从邮件里重新打开'
    return
  }
  try {
    await authApi.verifyEmail(token)
    state.value = 'ok'
    if (auth.user) await auth.refresh()
  } catch (error) {
    state.value = 'error'
    // 后端的提示是写给未登录的人看的（「请登录后重新发送」）；已登录时换个说法
    message.value = auth.user ? '这个链接已经失效：可能已经用过，或者超过了 24 小时。' : errorMessage(error)
  }
})

async function resend() {
  resending.value = true
  try {
    showToast((await authApi.resendVerification()).message)
  } catch (error) {
    showToast(errorMessage(error))
  } finally {
    resending.value = false
  }
}
</script>

<template>
  <AuthFrame>
    <section class="bc-card status" aria-live="polite">
      <Transition name="swap" mode="out-in">
        <div v-if="state === 'checking'" key="checking" class="state">
          <CompassMark :size="88" motion="seek" />
          <h1>正在验证邮箱</h1>
          <p class="sub">稍等一下……</p>
        </div>

        <div v-else-if="state === 'ok'" key="ok" class="state">
          <span class="badge ok"><AppIcon name="check" :size="34" /></span>
          <h1>邮箱验证成功</h1>
          <p class="sub">现在可以使用商业罗盘的全部功能了。</p>
          <van-button v-if="auth.user" type="primary" block to="/">开始使用</van-button>
          <van-button v-else type="primary" block to="/login">去登录</van-button>
        </div>

        <div v-else key="error" class="state">
          <span class="badge bad"><AppIcon name="alert" :size="34" /></span>
          <h1>没能验证</h1>
          <p class="sub">{{ message }}</p>
          <template v-if="auth.user && !auth.isVerified">
            <van-button type="primary" block :loading="resending" loading-text="正在发送…" @click="resend">
              重新发送验证邮件
            </van-button>
            <van-button block to="/">先回到首页</van-button>
          </template>
          <template v-else-if="auth.user">
            <p class="sub">你的邮箱其实已经验证过了。</p>
            <van-button type="primary" block to="/">回到首页</van-button>
          </template>
          <van-button v-else type="primary" block to="/login">登录后重新发送</van-button>
        </div>
      </Transition>
    </section>
  </AuthFrame>
</template>

<style scoped>
.status {
  padding-block: 32px 28px;
}
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}
.state .van-button {
  margin-top: 4px;
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
  animation: pop 0.45s var(--spring) both;
}
.badge.ok {
  background: var(--good-soft);
  color: var(--good);
}
.badge.bad {
  background: var(--bad-soft);
  color: var(--bad);
}
@keyframes pop {
  from {
    transform: scale(0.4);
    opacity: 0;
  }
}
.swap-enter-active,
.swap-leave-active {
  transition: opacity 0.2s var(--ease);
}
.swap-enter-from,
.swap-leave-to {
  opacity: 0;
}
</style>
