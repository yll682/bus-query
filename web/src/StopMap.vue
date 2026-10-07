<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import transform from 'coordtransform'
import type { Station } from './api'

const props = defineProps<{ stations: Station[]; lat: number; lng: number }>()
const emit = defineEmits<{ pick: [lat: number, lng: number] }>()
const element = ref<HTMLElement>()
const error = ref('')
let map: L.Map
onMounted(() => {
  const [lng, lat] = transform.gcj02towgs84(props.lng, props.lat)
  map = L.map(element.value!, { zoomControl: false }).setView([lat, lng], 15)
  L.control.zoom({ zoomInTitle: '放大地图', zoomOutTitle: '缩小地图' }).addTo(map)
  map.attributionControl.setPrefix(false)
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap 贡献者</a>',
  }).addTo(map)
  tiles.on('tileerror', () => { error.value = '地图图片加载失败，可以使用经纬度选择位置。' })
  L.circleMarker([lat, lng], { radius: 9, color: '#087d63', fillOpacity: 1 }).addTo(map).bindTooltip('查询位置')
  for (const station of props.stations.filter(item => item.coordinateSystem === 'GCJ02')) {
    const [x, y] = transform.gcj02towgs84(station.lng, station.lat)
    const label = document.createElement('span')
    label.textContent = station.name
    L.circleMarker([y, x], { radius: 6, color: '#214d71', fillOpacity: 0.8 }).addTo(map).bindTooltip(label)
  }
  map.on('click', event => {
    const [x, y] = transform.wgs84togcj02(event.latlng.lng, event.latlng.lat)
    emit('pick', y, x)
  })
})
onUnmounted(() => map.remove())
</script>

<template>
  <p class="hint">点击地图选择查询位置，地图数据来自 OpenStreetMap。</p>
  <div ref="element" class="stop-map" aria-label="站点地图"></div>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
</template>
