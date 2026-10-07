<script setup lang="ts">
import { ref, useId } from 'vue'
import { X } from '@lucide/vue'
import QueryDialog from './QueryDialog.vue'

defineProps<{ label: string }>()
const open = ref(false)
const titleId = useId()
</script>

<template>
  <button class="info-button" :aria-label="label" @click="open = true">ⓘ</button>
  <QueryDialog :open="open" :labelledby="titleId" @close="open = false">
    <div class="section-heading"><h2 :id="titleId">{{ label }}</h2><button class="round-button" @click="open = false" aria-label="关闭说明"><X :size="21" /></button></div>
    <div class="info-content"><slot /></div>
  </QueryDialog>
</template>
