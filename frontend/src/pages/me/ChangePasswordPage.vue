<script setup lang="ts">
/** 修改密码：成功后其他设备退出登录，当前设备保持登录 */
import { showToast, type FieldRule } from 'vant'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import { errorMessage } from '@/api/client'
import AppIcon from '@/components/AppIcon.vue'
import PageHead from '@/components/PageHead.vue'
import PasswordField from '@/components/PasswordField.vue'

const router = useRouter()
const form = reactive({ old: '', new: '' })
const submitting = ref(false)
const error = ref('')

const oldRules: FieldRule[] = [{ required: true, message: '请填写原密码' }]
const newRules: FieldRule[] = [
  { required: true, message: '请设置新密码' },
  { validator: (value: string) => value.length >= 8, message: '密码至少需要 8 位' },
]

async function onSubmit() {
  error.value = ''
  submitting.value = true
  try {
    const result = await authApi.changePassword({ old_password: form.old, new_password: form.new })
    showToast(result.message)
    await router.replace({ name: 'me' })
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page narrow">
    <PageHead title="修改密码" :back="{ name: 'me' }" back-label="我的" />
    <section class="bc-card">
      <van-form class="form-stack" @submit="onSubmit">
        <PasswordField v-model="form.old" label="原密码" name="old_password" autocomplete="current-password" :rules="oldRules" />
        <PasswordField
          v-model="form.new"
          label="新密码"
          name="new_password"
          autocomplete="new-password"
          placeholder="至少 8 位"
          :rules="newRules"
        />
        <p class="form-hint">修改后，其他设备上的登录会退出，这台设备保持登录。</p>
        <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="16" />{{ error }}</p>
        <van-button block type="primary" native-type="submit" :loading="submitting" loading-text="正在保存…">
          保存新密码
        </van-button>
      </van-form>
    </section>
  </div>
</template>

<style scoped>
.page.narrow {
  max-width: 640px;
}
</style>
