import { createPinia } from 'pinia'
import { showToast } from 'vant'
import { createApp } from 'vue'

// 数字字体：Barlow Semi Condensed，只含英文字母和数字，打包在网站里（不依赖 Google 字体）
import '@fontsource/barlow-semi-condensed/latin-500.css'
import '@fontsource/barlow-semi-condensed/latin-600.css'
// 以函数方式调用的 Vant 组件（showToast、showConfirmDialog）需要手动引入样式
import 'vant/es/toast/style'
import 'vant/es/dialog/style'
import './styles/theme.css'
import './styles/base.css'

import { setUnauthorizedHandler } from './api/client'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// 用着用着登录过期了（或在别的设备改了密码）：回到登录页，登录后回到原来的页面
setUnauthorizedHandler(() => {
  const auth = useAuthStore(pinia)
  if (!auth.user) return
  auth.clear()
  const current = router.currentRoute.value
  if (current.meta.requiresAuth) {
    showToast('登录已过期，请重新登录')
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})

void router.isReady().then(() => app.mount('#app'))
