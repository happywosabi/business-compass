<script setup lang="ts">
/** 我的：账号信息、修改密码、协议、退出登录 */
import { showConfirmDialog, showToast } from 'vant'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import PageHead from '@/components/PageHead.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()
const router = useRouter()

const initial = computed(() => auth.user?.email.charAt(0).toUpperCase() ?? '')
const joined = computed(() => (auth.user ? formatDate(auth.user.created_at) : ''))

const resending = ref(false)
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

async function logout() {
  try {
    await showConfirmDialog({
      title: '退出登录',
      message: '退出后需要重新输入邮箱和密码。',
      confirmButtonText: '退出登录',
      confirmButtonColor: 'var(--bad)',
      cancelButtonText: '取消',
    })
  } catch {
    return // 点了取消
  }
  await auth.logout().catch(() => undefined)
  showToast('已退出登录')
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="page narrow">
    <PageHead title="我的" />

    <section v-if="auth.user" class="bc-card account">
      <span class="avatar" aria-hidden="true">{{ initial }}</span>
      <div class="info">
        <p class="email">{{ auth.user.email }}</p>
        <p class="meta">
          <span v-if="auth.isVerified" class="pill ok"><AppIcon name="check" :size="13" />邮箱已验证</span>
          <span v-else class="pill warn">邮箱未验证</span>
          <span v-if="joined" class="sub">{{ joined }}注册</span>
        </p>
      </div>
      <van-button
        v-if="!auth.isVerified"
        size="small"
        class="resend"
        :loading="resending"
        loading-text="发送中"
        @click="resend"
      >
        重新发送验证邮件
      </van-button>
    </section>

    <van-cell-group inset class="menu">
      <van-cell title="修改密码" is-link to="/me/password">
        <template #icon><AppIcon name="lock" class="cell-icon" /></template>
      </van-cell>
      <van-cell title="用户协议" is-link to="/terms">
        <template #icon><AppIcon name="doc" class="cell-icon" /></template>
      </van-cell>
      <van-cell title="隐私政策" is-link to="/privacy">
        <template #icon><AppIcon name="doc" class="cell-icon" /></template>
      </van-cell>
    </van-cell-group>

    <p class="disclaimer">测算结果基于你提供的估计和行业默认值，仅供参考，不构成投资建议。</p>

    <van-button block class="logout" @click="logout">
      <span class="btn-inner"><AppIcon name="logout" :size="18" />退出登录</span>
    </van-button>
  </div>
</template>

<style scoped>
.page.narrow {
  max-width: 640px;
}
.account {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
}
.avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--ink);
  color: var(--surface);
  font-family: var(--font-num);
  font-size: 22px;
  font-weight: 600;
}
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.email {
  font-size: 17px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.8;
  padding: 0 9px;
  border-radius: 999px;
}
.pill.ok {
  background: var(--good-soft);
  color: var(--good);
}
.pill.warn {
  background: var(--warn-soft);
  color: var(--warn);
}
.resend {
  width: 100%;
}
@media (min-width: 768px) {
  .resend {
    width: auto;
  }
}
.menu.van-cell-group--inset {
  margin: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
}
.menu :deep(.van-cell) {
  padding: 14px 16px;
  align-items: center;
}
.cell-icon {
  margin-right: 10px;
  color: var(--muted);
}
.disclaimer {
  font-size: 13px;
  color: var(--faint);
  padding: 0 4px;
}
.btn-inner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.logout {
  color: var(--bad);
}
</style>
