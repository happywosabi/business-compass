/**
 * 页面路由。网址和后端邮件里的链接一致：/verify-email、/reset-password。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { DESKTOP_QUERY } from '@/composables/useBreakpoint'
import AppShell from '@/layouts/AppShell.vue'
import AuthPage from '@/pages/auth/AuthPage.vue'
import { useAuthStore } from '@/stores/auth'
import { safeRedirect } from '@/utils/redirect'

const LegalPage = () => import('@/pages/legal/LegalPage.vue')

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: AuthPage, meta: { title: '登录', guestOnly: true } },
  { path: '/register', name: 'register', component: AuthPage, meta: { title: '注册', guestOnly: true } },
  {
    path: '/verify-email',
    name: 'verify-email',
    component: () => import('@/pages/auth/VerifyEmailPage.vue'),
    meta: { title: '验证邮箱' },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('@/pages/auth/ResetPasswordPage.vue'),
    meta: { title: '重置密码' },
  },
  { path: '/terms', name: 'terms', component: LegalPage, props: { doc: 'terms' }, meta: { title: '用户协议' } },
  { path: '/privacy', name: 'privacy', component: LegalPage, props: { doc: 'privacy' }, meta: { title: '隐私政策' } },
  {
    // 登录后的页面都在这个外框里：桌面左侧导航栏，手机底部标签栏
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/pages/home/HomePage.vue'),
        meta: { title: '我的档案', nav: 'home', depth: 1 },
      },
      {
        path: 'me',
        name: 'me',
        component: () => import('@/pages/me/MePage.vue'),
        meta: { title: '我的', nav: 'me', depth: 1 },
      },
      {
        path: 'me/password',
        name: 'change-password',
        component: () => import('@/pages/me/ChangePasswordPage.vue'),
        meta: { title: '修改密码', nav: 'me', depth: 2 },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFoundPage.vue'),
    meta: { title: '页面不存在' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, saved) {
    return saved ?? { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureLoaded()
  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.user) {
    return safeRedirect(to.query.redirect)
  }
})

router.afterEach((to, from) => {
  document.title = to.meta.title ? `${to.meta.title} - 商业罗盘` : '商业罗盘'

  // 页面切换动画：桌面和同级页面淡入；手机进入更深的页面从右边推入，返回时反向
  const toDepth = to.meta.depth ?? 0
  const fromDepth = from.meta.depth ?? 0
  const desktop = window.matchMedia(DESKTOP_QUERY).matches
  if (desktop || toDepth === fromDepth) to.meta.transition = 'page-fade'
  else to.meta.transition = toDepth > fromDepth ? 'page-push' : 'page-pop'
})
