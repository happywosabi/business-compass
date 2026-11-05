/**
 * 按屏幕宽度切换布局（docs/前端设计.md 12.2）。
 * 只改样式的地方用 CSS 媒体查询；需要换组件结构时（如手机底部导航、桌面侧边栏）用这里。
 */

import { onScopeDispose, ref, type Ref } from 'vue'

export const DESKTOP_QUERY = '(min-width: 768px)'

export function useMedia(query: string): Ref<boolean> {
  const list = window.matchMedia(query)
  const matches = ref(list.matches)
  const update = (event: MediaQueryListEvent) => {
    matches.value = event.matches
  }
  list.addEventListener('change', update)
  onScopeDispose(() => list.removeEventListener('change', update))
  return matches
}

export function useBreakpoint() {
  return {
    /** 768px 及以上：左侧导航栏布局 */
    isDesktop: useMedia(DESKTOP_QUERY),
  }
}
