/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import { VantResolver } from '@vant/auto-import-resolver'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

/**
 * Vant 的图标字体已经内嵌在 CSS 里，但它还写了一个备用地址（at.alicdn.com）。
 * 浏览器有时会多请求一次这个外部地址，被网站的安全策略拦下后在控制台报错。
 * 打包时把这个备用地址删掉，只用内嵌的字体。
 */
const dropRemoteVantFont = {
  postcssPlugin: 'drop-remote-vant-font',
  AtRule: {
    'font-face': (rule: { walkDecls: (prop: string, fn: (decl: { value: string }) => void) => void }) => {
      rule.walkDecls('src', (decl) => {
        decl.value = decl.value
          .split(/,(?=\s*url\()/)
          .filter((source) => !source.includes('alicdn.com'))
          .join(',')
      })
    },
  },
}

export default defineConfig({
  css: { postcss: { plugins: [dropRemoteVantFont] } },
  plugins: [
    vue(),
    // 模板里直接写 <van-button> 等 Vant 组件即可，不用逐个 import，样式也会按需引入
    Components({ resolvers: [VantResolver()], dts: 'src/components.d.ts' }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // 开发时把 /api 请求转发给 Docker 里的后端（经过 Nginx，和线上一样带限流）
    proxy: { '/api': 'http://localhost:8080' },
  },
  build: {
    // 照顾老一些的手机和微信内置浏览器
    target: ['es2020', 'chrome87', 'safari14'],
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
