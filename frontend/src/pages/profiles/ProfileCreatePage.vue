<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { profilesApi, type Template } from '@/api/profiles'
import { errorMessage } from '@/api/client'
import PageHead from '@/components/PageHead.vue'
import CompassMark from '@/components/CompassMark.vue'
import { PROFILE_STAGES } from '@/utils/parameters'
const router = useRouter()
const templates = ref<Template[]>([])
const form = reactive({
  name: '',
  city: '',
  industry: 'drinks',
  template_key: 'physical_store' as 'physical_store' | 'orchard',
  stage: 'idea' as 'idea' | 'preparing' | 'operating',
})
const selectedTemplate = computed(() => templates.value.find((t) => t.key === form.template_key))
const orchard = computed(() => form.template_key === 'orchard')
watch(orchard, (value) => {
  form.industry = value ? 'fruit_grower' : 'drinks'
  form.stage = value ? 'operating' : 'idea'
})
const saving = ref(false),
  error = ref('')
onMounted(async () => {
  try {
    templates.value = await profilesApi.templates()
  } catch (e) {
    error.value = errorMessage(e)
  }
})
async function create() {
  saving.value = true
  error.value = ''
  try {
    const profile = await profilesApi.create(form)
    await router.replace(`/profiles/${profile.id}/interview`)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <div class="page create-page">
    <PageHead title="给你的想法，建一份档案" back="/" back-label="我的档案" />
    <div class="create-grid">
      <section class="create-intro chart-grid">
        <CompassMark :size="130" motion="settle" /><span class="eyebrow">从一个想法开始</span>
        <h2>先记下来，<br />再一步步算清楚。</h2>
        <p>
          {{
            orchard
              ? '把一年的收成与投入慢慢记清，给每个品种找到合适的销路。数字可以分次补，也可以随时修改。'
              : '还没确定铺面、拿不准客流，都没关系。每一个数字都可以慢慢补，也可以随时修改。'
          }}
        </p>
        <div class="intro-route">
          <span>建档案</span><i /><span>聊想法</span><i /><span>看结果</span>
        </div>
      </section>
      <form class="bc-card form-stack create-form" @submit.prevent="create">
        <span class="eyebrow">你的第一步</span>
        <fieldset class="stage-select">
          <legend>选择经营档案</legend>
          <label
            v-for="t in templates"
            :key="t.key"
            :class="{ selected: form.template_key === t.key }"
            ><input v-model="form.template_key" type="radio" :value="t.key" /><span>{{
              t.label
            }}</span></label
          >
        </fieldset>
        <label class="input-label"
          ><span>{{ orchard ? '给你的果园起个名字' : '给这家店起个名字' }}</span
          ><input
            v-model="form.name"
            class="bc-input"
            :placeholder="orchard ? '比如：山间红心蜜柚果园' : '比如：大学城奶茶店'"
            maxlength="80"
            required
            autofocus
        /></label>
        <label class="input-label"
          ><span>{{ orchard ? '果园生产地在哪个城市' : '打算开在哪个城市' }}</span
          ><input
            v-model="form.city"
            class="bc-input"
            placeholder="比如：杭州"
            maxlength="60"
            required
        /></label>
        <label class="input-label"
          ><span>{{ orchard ? '经营类型' : '准备开什么店' }}</span
          ><select v-model="form.industry" class="bc-input">
            <option
              v-for="industry in selectedTemplate?.industries ?? []"
              :key="industry.code"
              :value="industry.code"
            >
              {{ industry.label }}
            </option>
          </select></label
        >
        <p class="sub">
          {{
            orchard
              ? '适用于已投产果园，支持多品种、批发与零售，以经营期总账看清收成。'
              : '从饮品店开始，一步步算清投入与经营。'
          }}
        </p>
        <fieldset v-if="!orchard" class="stage-select">
          <legend>现在到哪一步了</legend>
          <label
            v-for="(label, key) in PROFILE_STAGES"
            :key="key"
            :class="{ selected: form.stage === key }"
            ><input v-model="form.stage" type="radio" :value="key" /><span>{{ label }}</span></label
          >
        </fieldset>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <van-button
          type="primary"
          native-type="submit"
          block
          :loading="saving"
          :disabled="!templates.length"
          >建好档案，和 AI 聊聊 →</van-button
        >
        <p class="sub">建好后进入 AI 访谈，也可以选择手动填写。档案仅自己可见。</p>
      </form>
    </div>
  </div>
</template>
<style scoped>
.create-page {
  max-width: 1050px;
}
.create-grid {
  display: grid;
  gap: 20px;
}
.create-intro {
  padding: 30px;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: flex-start;
  animation: compass-rise 0.6s var(--ease) both;
}
.create-intro h2 {
  font-size: 30px;
  line-height: 1.4;
}
.create-intro p {
  font-size: 14px;
  color: var(--muted);
  max-width: 28em;
}
.create-intro > svg {
  align-self: center;
}
.intro-route {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--accent-ink);
  font-size: 12px;
  margin-top: 15px;
}
.intro-route i {
  width: 26px;
  height: 1px;
  background: var(--accent-line);
}
.create-form {
  animation: compass-rise 0.6s 0.1s var(--ease) both;
}
.stage-select {
  border: 0;
  padding: 0;
  display: flex;
  gap: 8px;
  margin: 0;
}
.stage-select legend {
  font-size: 14px;
  color: var(--muted);
  margin-bottom: 8px;
}
.stage-select label {
  flex: 1;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 6px;
  font-size: 13px;
  cursor: pointer;
  transition: 0.2s;
}
.stage-select label.selected {
  color: var(--accent-ink);
  background: var(--accent-soft);
  border-color: var(--accent-line);
}
.stage-select input {
  position: absolute;
  opacity: 0;
}
.stage-select label:focus-within {
  outline: 2px solid var(--accent);
}
@media (min-width: 1024px) {
  .create-grid {
    grid-template-columns: 0.9fr 1.1fr;
    gap: 30px;
  }
  .create-intro {
    padding: 32px;
  }
  .create-form {
    padding: 30px;
  }
}
@media (max-width: 767px) {
  .create-intro > svg {
    width: 72px;
    height: 72px;
    align-self: flex-start;
  }
  .create-intro h2 {
    font-size: 24px;
  }
}
</style>
