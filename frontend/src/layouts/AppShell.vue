<script setup lang="ts">
/**
 * 登录后的外框（docs/前端设计.md 12.2、12.3）：
 * - 768px 及以上：左侧导航栏（1200px 以下只显示图标）
 * - 768px 以下：底部标签栏
 * 邮箱未验证时，页面顶部显示提示条。
 */
import { showToast } from 'vant'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import CompassMark from '@/components/CompassMark.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const { isDesktop } = useBreakpoint()

const activeNav = computed(() => route.meta.nav ?? 'home')
const initial = computed(() => auth.user?.email.charAt(0).toUpperCase() ?? '')

const resending = ref(false)
async function resend() {
  resending.value = true
  try {
    const result = await authApi.resendVerification()
    showToast(result.message)
  } catch (error) {
    showToast(errorMessage(error))
  } finally {
    resending.value = false
  }
}

// 用户可能在另一个标签页点了验证链接：切回来时重新检查一次
function onVisible() {
  if (document.visibilityState === 'visible' && auth.user && !auth.isVerified) void auth.refresh()
}
onMounted(() => document.addEventListener('visibilitychange', onVisible))
onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisible))
</script>

<template>
  <div class="shell" :class="{ desktop: isDesktop }">
    <aside v-if="isDesktop" class="side" aria-label="导航">
      <RouterLink class="brand" to="/" title="商业罗盘">
        <CompassMark :size="28" simple dark />
        <span class="lbl">商业罗盘</span>
      </RouterLink>
      <nav class="snav" aria-label="主导航">
        <RouterLink
          class="sitem"
          to="/"
          title="档案"
          :aria-current="activeNav === 'home' ? 'page' : undefined"
        >
          <AppIcon name="profiles" />
          <span class="lbl">档案</span>
        </RouterLink>
        <RouterLink
          class="sitem"
          to="/content"
          title="内容"
          :aria-current="activeNav === 'content' ? 'page' : undefined"
        >
          <AppIcon name="content" />
          <span class="lbl">内容</span>
        </RouterLink>
      </nav>
      <RouterLink
        class="suser"
        to="/me"
        title="我的账号"
        :aria-current="activeNav === 'me' ? 'page' : undefined"
      >
        <span class="avatar" aria-hidden="true">{{ initial }}</span>
        <span class="who lbl">
          <span class="email">{{ auth.user?.email }}</span>
          <span class="hint">我的账号</span>
        </span>
      </RouterLink>
    </aside>

    <div class="main chart-grid">
      <Transition name="bar">
        <div v-if="auth.user && !auth.isVerified" class="verify-bar" role="status">
          <AppIcon name="mail" :size="18" />
          <span class="vb-text">
            邮箱还没验证。打开 <b>{{ auth.user.email }}</b> 收到的邮件，点里面的链接，验证后就能用
            AI 功能。
          </span>
          <button type="button" class="text-link vb-btn" :disabled="resending" @click="resend">
            {{ resending ? '正在发送…' : '重新发送' }}
          </button>
        </div>
      </Transition>

      <RouterView v-slot="{ Component, route: current }">
        <Transition :name="current.meta.transition ?? 'page-fade'" mode="out-in">
          <component :is="Component" :key="current.path" />
        </Transition>
      </RouterView>
    </div>

    <van-tabbar v-if="!isDesktop" :model-value="activeNav" fixed placeholder safe-area-inset-bottom>
      <van-tabbar-item name="home" to="/">
        <template #icon><AppIcon name="profiles" :size="22" /></template>
        档案
      </van-tabbar-item>
      <van-tabbar-item name="content" to="/content"
        ><template #icon><AppIcon name="content" :size="22" /></template>内容</van-tabbar-item
      >
      <van-tabbar-item name="me" to="/me">
        <template #icon><AppIcon name="user" :size="22" /></template>
        我的
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  min-height: 100dvh;
}
.shell.desktop {
  display: grid;
  grid-template-columns: var(--side-w) minmax(0, 1fr);
}
.main {
  min-width: 0;
  min-height: 100vh;
  min-height: 100dvh;
}

/* ---- 左侧导航栏 ---- */
.side {
  position: sticky;
  top: 0;
  height: 100vh;
  height: 100dvh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 20px 14px 16px;
  background: var(--side);
  color: var(--side-ink);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px;
  font-size: 17px;
  font-weight: 700;
  text-decoration: none;
}
.snav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sitem,
.suser {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  color: var(--side-ink);
  font-size: 15px;
  text-decoration: none;
  transition: background-color 0.15s;
}
a.sitem:hover,
.suser:hover {
  background: var(--side-hover);
}
.sitem[aria-current='page'],
.suser[aria-current='page'] {
  background: var(--side-active);
}
.sitem.off {
  color: var(--side-muted);
}
.soon {
  margin-left: auto;
  font-size: 11px;
  line-height: 1.7;
  padding: 0 7px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 999px;
}
.suser {
  margin-top: auto;
  padding: 10px 8px;
}
.avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--surface);
  font-family: var(--font-num);
  font-weight: 600;
  font-size: 14px;
}
.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.4;
}
.email {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.who .hint {
  font-size: 12px;
  color: var(--side-muted);
}

/* 768–1199px：导航栏只显示图标 */
@media (max-width: 1199px) {
  .shell.desktop {
    grid-template-columns: 72px minmax(0, 1fr);
  }
  .side {
    align-items: center;
    padding-inline: 12px;
  }
  .side .lbl {
    display: none;
  }
  .brand,
  .sitem,
  .suser {
    justify-content: center;
    width: 44px;
    padding-inline: 0;
  }
}

/* ---- 邮箱未验证提示条 ---- */
.verify-bar {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px max(16px, env(safe-area-inset-right, 0px)) 10px
    max(16px, env(safe-area-inset-left, 0px));
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-bottom: 1px solid var(--accent-line);
  font-size: 14px;
  line-height: 1.55;
}
.verify-bar .app-icon {
  margin-top: 2px;
}
.vb-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.vb-btn {
  flex: none;
  color: var(--accent-ink);
  font-size: 14px;
}
.vb-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
@media (min-width: 768px) {
  .verify-bar {
    align-items: center;
    padding-inline: 32px;
  }
}
.bar-enter-active,
.bar-leave-active {
  transition: opacity 0.25s var(--ease);
}
.bar-enter-from,
.bar-leave-to {
  opacity: 0;
}

/* ---- 底部标签栏 ---- */
:deep(.van-tabbar) {
  border-top: 1px solid var(--line-soft);
}
:deep(.van-tabbar::after) {
  display: none;
}
:deep(.van-tabbar-item__icon) {
  margin-bottom: 2px;
}
</style>
