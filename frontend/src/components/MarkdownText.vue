<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
const props = defineProps<{ content: string }>()
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true })
// 默认协议过滤保留；外部链接不携带本页引用信息。
const renderLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, i, options, env, self) => {
  tokens[i]!.attrSet('rel', 'noopener noreferrer')
  tokens[i]!.attrSet('target', '_blank')
  return renderLink
    ? renderLink(tokens, i, options, env, self)
    : self.renderToken(tokens, i, options)
}
const html = computed(() => markdown.render(props.content))
</script>
<template><div class="markdown-text" v-html="html" /></template>
<style scoped>
.markdown-text {
  font-size: 14px;
  line-height: 1.9;
  overflow-wrap: anywhere;
}
.markdown-text :deep(p + p) {
  margin-top: 12px;
}
.markdown-text :deep(h2),
.markdown-text :deep(h3) {
  font-size: 16px;
  margin: 16px 0 8px;
}
.markdown-text :deep(ul),
.markdown-text :deep(ol) {
  padding-left: 22px;
}
.markdown-text :deep(a) {
  color: var(--accent-ink);
}
.markdown-text :deep(pre) {
  overflow: auto;
  padding: 12px;
  background: var(--surface-2);
  border-radius: 6px;
}
</style>
