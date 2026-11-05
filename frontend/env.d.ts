/// <reference types="vite/client" />

import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 浏览器标签页上显示的标题 */
    title?: string
    /** 需要登录才能访问 */
    requiresAuth?: boolean
    /** 已登录时不显示（登录、注册页），直接进入应用 */
    guestOnly?: boolean
    /** 对应底部导航 / 侧边栏的哪一项 */
    nav?: 'home' | 'me'
    /** 页面层级：手机上进入更深的页面从右边推入，返回时反向 */
    depth?: number
    /** 页面切换动画名称，由路由在每次跳转后设置 */
    transition?: string
  }
}
