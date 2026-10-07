<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { BusFront } from '@lucide/vue'
import type { RouteStation, Vehicle } from './api'

const props = defineProps<{ stations: RouteStation[]; vehicles: Vehicle[]; selected?: number; selectable: boolean }>()
const emit = defineEmits<{ select: [order: number] }>()
const scroller = ref<HTMLElement>()
function atStop(order: number) { return props.vehicles.filter(vehicle => vehicle.order === order) }
async function revealSelection() {
  await nextTick()
  const element = scroller.value?.querySelector<HTMLElement>('[aria-pressed="true"]')
  if (!element || !scroller.value) return
  const container = scroller.value.getBoundingClientRect()
  const stop = element.getBoundingClientRect()
  scroller.value.scrollTo({ left: Math.max(0, scroller.value.scrollLeft + stop.left - container.left - scroller.value.clientWidth / 2 + stop.width / 2), behavior: 'instant' })
}
watch(() => [props.selected, props.stations], revealSelection)
onMounted(revealSelection)
</script>

<template>
  <div ref="scroller" class="route-diagram" tabindex="0" aria-label="沿途站点图，左右滑动查看全部站点">
    <ol class="diagram-track">
      <li v-for="station in stations" :key="station.order" :class="{ current: selectable && selected === station.order }">
        <component :is="selectable ? 'button' : 'div'" class="diagram-stop" :aria-pressed="selectable ? selected === station.order : undefined" :aria-label="`${station.order}. ${station.name}${selectable ? '，选择乘车站' : ''}`" @click="selectable && emit('select', station.order)">
          <span class="diagram-vehicles" :title="atStop(station.order).map(vehicle => vehicle.plate).join('、')"><template v-if="atStop(station.order).length"><BusFront :size="17" /><span>{{ atStop(station.order).length }}</span></template></span>
          <span class="diagram-order">{{ station.order }}</span>
          <span class="diagram-name">{{ station.name }}</span>
        </component>
      </li>
    </ol>
  </div>
</template>
