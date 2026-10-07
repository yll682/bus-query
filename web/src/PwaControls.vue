<script setup lang="ts">
import { onMounted, onUnmounted, ref, useId } from 'vue'
import { Download, RefreshCw, X } from '@lucide/vue'
import { useRegisterSW } from 'virtual:pwa-register/vue'
import QueryDialog from './QueryDialog.vue'

interface InstallPrompt extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

defineProps<{ showInstall: boolean }>()
const standalone = window.matchMedia('(display-mode: standalone)')
const isInstalled = ref(standalone.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true || localStorage.getItem('bus.pwaInstalled') === 'true')
const installDialog = ref(false)
const installing = ref(false)
const titleId = useId()
const installPrompt = ref<InstallPrompt>()
const online = ref(navigator.onLine)
const installError = ref('')
const { needRefresh, updateServiceWorker } = useRegisterSW({
  immediate: true,
  onRegisterError(error) { installError.value = `PWA 注册失败：${error.message}` },
})

function offerInstall(event: Event) {
  event.preventDefault()
  if (standalone.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true) return
  isInstalled.value = false
  localStorage.removeItem('bus.pwaInstalled')
  installPrompt.value = event as InstallPrompt
}
function installed() {
  isInstalled.value = true
  installPrompt.value = undefined
  installDialog.value = false
  localStorage.setItem('bus.pwaInstalled', 'true')
}
function displayModeChanged() { if (standalone.matches) installed() }
function connectionChanged() { online.value = navigator.onLine }
async function install() {
  const prompt = installPrompt.value
  if (!prompt) { installDialog.value = true; return }
  installing.value = true
  try {
    await prompt.prompt()
    await prompt.userChoice
    installPrompt.value = undefined
  } finally { installing.value = false }
}
onMounted(() => {
  if (isInstalled.value) installed()
  standalone.addEventListener('change', displayModeChanged)
  window.addEventListener('beforeinstallprompt', offerInstall)
  window.addEventListener('appinstalled', installed)
  window.addEventListener('online', connectionChanged)
  window.addEventListener('offline', connectionChanged)
})
onUnmounted(() => {
  standalone.removeEventListener('change', displayModeChanged)
  window.removeEventListener('beforeinstallprompt', offerInstall)
  window.removeEventListener('appinstalled', installed)
  window.removeEventListener('online', connectionChanged)
  window.removeEventListener('offline', connectionChanged)
})
</script>

<template>
  <div v-if="!online" class="offline-banner" role="status">当前离线 · 实时查询已暂停</div>
  <div v-if="needRefresh" class="pwa-update" role="status"><span>新版本可用</span><button class="text-button" @click="updateServiceWorker(true)"><RefreshCw :size="16" />更新</button><button class="round-button" @click="needRefresh = false" aria-label="稍后更新"><X :size="17" /></button></div>
  <div v-if="installError" class="error" role="alert">{{ installError }}</div>
  <div v-if="showInstall && !isInstalled" class="pwa-actions"><button class="text-button" :disabled="installing" @click="install"><Download :size="16" />安装候车</button></div>
  <QueryDialog :open="installDialog && showInstall && !isInstalled" :labelledby="titleId" @close="installDialog = false">
    <div class="section-heading"><h2 :id="titleId">安装候车</h2><button class="round-button" @click="installDialog = false" aria-label="关闭安装说明"><X :size="21" /></button></div>
    <div class="info-content"><p>在浏览器菜单中选择安装应用或添加到桌面。iPhone、iPad 可在 Safari 分享菜单选择添加到主屏幕。</p><p>需要 HTTPS 或 localhost。页面资源可离线打开，实时公交查询需要联网。收藏保留在当前设备。</p></div>
  </QueryDialog>
</template>
