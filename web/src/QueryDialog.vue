<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; labelledby: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()

function syncOpen() {
  if (!dialog.value) return
  if (props.open && !dialog.value.open) dialog.value.showModal()
  if (!props.open && dialog.value.open) dialog.value.close()
}

function closeOutside(event: MouseEvent) {
  if (event.target !== dialog.value) return
  const bounds = dialog.value!.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) emit('close')
}

watch(() => props.open, syncOpen, { flush: 'post' })
onMounted(syncOpen)
</script>

<template>
  <dialog ref="dialog" class="modal" aria-modal="true" :aria-labelledby="labelledby" @cancel.prevent="emit('close')" @click="closeOutside">
    <slot v-if="open" />
  </dialog>
</template>
