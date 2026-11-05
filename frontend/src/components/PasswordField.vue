<script setup lang="ts">
/** 密码输入框，右侧带「显示 / 隐藏密码」按钮 */
import type { FieldRule } from 'vant'
import { ref } from 'vue'

import AppIcon from './AppIcon.vue'

const model = defineModel<string>({ required: true })
defineProps<{
  label: string
  name: string
  autocomplete: 'current-password' | 'new-password'
  placeholder?: string
  rules?: FieldRule[]
}>()

const visible = ref(false)
</script>

<template>
  <van-field
    v-model="model"
    class="bc-field"
    label-align="top"
    :label="label"
    :name="name"
    :type="visible ? 'text' : 'password'"
    :autocomplete="autocomplete"
    :placeholder="placeholder"
    :rules="rules"
    autocapitalize="off"
    :spellcheck="false"
  >
    <template #right-icon>
      <button
        type="button"
        class="pw-toggle"
        :aria-label="visible ? '隐藏密码' : '显示密码'"
        :aria-pressed="visible"
        @click="visible = !visible"
      >
        <AppIcon :name="visible ? 'eye-off' : 'eye'" />
      </button>
    </template>
  </van-field>
</template>
