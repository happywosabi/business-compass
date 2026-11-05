<script setup lang="ts">
import { ref, watch, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { evaluationsApi, type Evaluation, isFruitEvaluation } from '@/api/evaluations'
import { profilesApi, type Profile } from '@/api/profiles'
import { errorMessage } from '@/api/client'
const FruitResult = defineAsyncComponent(() => import('./FruitRetailResultPage.vue'))
const StoreResult = defineAsyncComponent(() => import('./StoreResultPage.vue'))
const OrchardResult = defineAsyncComponent(() => import('./OrchardResultPage.vue'))
const route = useRoute()
const snapshot = ref<Evaluation>(),
  profile = ref<Profile>(),
  error = ref('')
let sequence = 0
async function load() {
  const ticket = ++sequence
  snapshot.value = undefined
  error.value = ''
  try {
    const [e, p] = await Promise.all([
      evaluationsApi.get(String(route.params.id), String(route.params.eid)),
      profilesApi.get(String(route.params.id)),
    ])
    if (ticket !== sequence) return
    snapshot.value = e
    profile.value = p
  } catch (e) {
    if (ticket === sequence) error.value = errorMessage(e)
  }
}
watch(() => route.fullPath, load, { immediate: true })
</script>
<template>
  <div class="result-dispatch">
    <FruitResult
      v-if="snapshot && profile && isFruitEvaluation(snapshot)"
      :key="snapshot.id"
      :snapshot="snapshot"
      :profile="profile"
    />
    <OrchardResult
      v-else-if="snapshot?.template_key === 'orchard' && profile"
      :key="snapshot.id"
      :snapshot="snapshot"
      :profile="profile"
    />
    <StoreResult v-else-if="snapshot?.template_key === 'physical_store'" :key="snapshot.id" />
    <div v-else class="page">
      <p v-if="error" class="form-error" role="alert">
        {{ error }} <button class="text-link" @click="load">重试</button>
      </p>
      <div v-else class="bc-card skeleton" style="height: 220px" />
    </div>
  </div>
</template>

<style scoped>
.result-dispatch {
  min-width: 0;
}
</style>
