<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Download, RefreshCw, X } from '@lucide/vue'
import { useRegisterSW } from 'virtual:pwa-register/vue'
import InfoTip from './InfoTip.vue'

interface InstallPrompt extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const installPrompt = ref<InstallPrompt>()
const online = ref(navigator.onLine)
const installError = ref('')
const { needRefresh, updateServiceWorker } = useRegisterSW({
  immediate: true,
  onRegisterError(error) { installError.value = `PWA 注册失败：${error.message}` },
})

function offerInstall(event: Event) {
  event.preventDefault()
  installPrompt.value = event as InstallPrompt
}
function installed() { installPrompt.value = undefined }
function connectionChanged() { online.value = navigator.onLine }
async function install() {
  const prompt = installPrompt.value!
  await prompt.prompt()
  await prompt.userChoice
  installPrompt.value = undefined
}
onMounted(() => {
  window.addEventListener('beforeinstallprompt', offerInstall)
  window.addEventListener('appinstalled', installed)
  window.addEventListener('online', connectionChanged)
  window.addEventListener('offline', connectionChanged)
})
onUnmounted(() => {
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
  <div class="pwa-actions"><button v-if="installPrompt" class="text-button" @click="install"><Download :size="16" />安装候车</button><InfoTip label="安装到桌面"><p>支持 PWA，可添加到桌面并使用独立窗口打开。浏览器提供安装入口时可直接安装；iPhone、iPad 可在 Safari 分享菜单选择添加到主屏幕。</p><p>需要 HTTPS 或 localhost。页面资源可离线打开，实时公交查询需要联网。收藏保留在当前设备。</p></InfoTip></div>
</template>
