<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, BusFront, ChevronDown, ChevronRight, Clock3, Heart, LocateFixed, MapPin, RefreshCw, Search, Settings2, X } from '@lucide/vue'
import transform from 'coordtransform'
import QueryDialog from './QueryDialog.vue'
import InfoTip from './InfoTip.vue'
import PwaControls from './PwaControls.vue'
import RouteDiagram from './RouteDiagram.vue'
import { api, type Arrival, type City, type LineSummary, type Position, type Result, type Route, type SavedLine, type SavedStation, type SearchResults, type Station, type StationBus, type Timetable, type Vehicle } from './api'
import { vehiclePosition } from './vehiclePosition'

const StopMap = defineAsyncComponent(() => import('./StopMap.vue'))
const cities = ref<City[]>([])
const city = ref<City>()
const locatedCity = ref<City>()
const locationError = ref('')
const pendingPosition = ref<Position>()
const cityFilter = ref('')
const selectedProvince = ref('')
const cityDialog = ref(false)
const positionDialog = ref(false)
const mapVisible = ref(false)
const manualLat = ref('')
const manualLng = ref('')
const positionKeyword = ref('')
const positionResults = ref<{ name: string }[]>([])
const positionSearched = ref(false)
const positionBusy = ref(false)
const positionError = ref('')
const coordinateVisible = ref(false)
const stopDialog = ref(false)
const stopFilter = ref('')
const platformDialog = ref(false)
const lineFilter = ref('')
const position = ref<Position>()
const view = ref<'home' | 'search' | 'station' | 'route' | 'saved'>('home')
const busy = ref(false)
const locating = ref(false)
const error = ref('')
const locationStatus = ref('正在申请位置权限')
const nearby = ref<Station[]>([])
const nearbyTime = ref('')
const nearbyBuses = ref<Record<string, StationBus[]>>({})
const nearbyErrors = ref<Record<string, string>>({})
const expandedStations = ref<string[]>([])
const routePanel = ref<'diagram' | 'vehicles'>('diagram')
const keyword = ref('')
const searchResults = ref<SearchResults>({ lines: [], stations: [] })
const searched = ref(false)
const selectedStation = ref<Station>()
const stationBuses = ref<StationBus[]>([])
const route = ref<Route>()
const stopsError = ref('')
const selectedOrder = ref<number>()
const vehicles = ref<Vehicle[]>([])
const arrivals = ref<Arrival[]>([])
const vehicleNotice = ref('')
const nextDeparture = ref('')
const liveTime = ref('')
const liveError = ref('')
const refreshing = ref(false)
const timetable = ref<Timetable>()
const timetableVisible = ref(false)
const savedLines = ref<SavedLine[]>(JSON.parse(localStorage.getItem('bus.savedLines') || '[]'))
const savedStations = ref<SavedStation[]>(JSON.parse(localStorage.getItem('bus.savedStations') || '[]'))
const history = ref<string[]>(JSON.parse(localStorage.getItem('bus.history') || '[]'))
let epoch = 0
let liveSequence = 0
let searchSequence = 0
let locationSequence = 0
let positionSequence = 0
let nearbySequence = 0
let timer: ReturnType<typeof setTimeout>
let restoring = true
type PageState = {
  view: typeof view.value; route: Route | undefined; station: Station | undefined
  order: number | undefined; keyword: string
  results: typeof searchResults.value; searched: boolean; stopsError: string; scroll: number
}
const previousPages = ref<PageState[]>([])
const searchInput = ref<HTMLInputElement>()

const isXiamen = computed(() => city.value?.code === '0592')
const provinceOptions = computed(() => [...new Set(cities.value.map(item => item.province || '其他地区'))])
const cityOptions = computed(() => cities.value.filter(item => cityFilter.value.trim()
  ? `${item.name} ${item.province} ${item.pinyin}`.toLowerCase().includes(cityFilter.value.trim().toLowerCase())
  : (item.province || '其他地区') === selectedProvince.value))
const selectedRouteStation = computed(() => route.value?.stations.find(item => item.order === selectedOrder.value))
const routeSaved = computed(() => savedLines.value.some(item => item.city.key === city.value?.key && item.name === route.value?.name && item.direction === route.value?.direction))
const stationSaved = computed(() => savedStations.value.some(item => item.city.key === city.value?.key && stationKey(item.station) === (selectedStation.value ? stationKey(selectedStation.value) : '')))
const nearest = computed(() => nearby.value[0])
const matchingStops = computed(() => route.value?.stations.filter(item => item.name.includes(stopFilter.value.trim())) || [])
const stationLines = computed(() => selectedStation.value?.lines.filter(item => `${item.name} ${item.to}`.includes(lineFilter.value.trim())) || [])
const otherPlatforms = computed(() => selectedStation.value?.platformNumbers?.filter(number => number !== selectedStation.value?.number) || [])
const nationalPlatforms = computed(() => selectedStation.value?.platforms?.filter(item => item.lat !== selectedStation.value?.lat || item.lng !== selectedStation.value?.lng) || [])
const pageNames = { home: '附近站点', search: '搜索结果', station: '站点详情', route: '线路详情', saved: '我的收藏' }
const backLabel = computed(() => `返回${pageNames[previousPages.value.at(-1)?.view || 'home']}`)
const timetableGroups = computed(() => {
  if (timetable.value?.groups) return timetable.value.groups.map((group, index) => ({
    name: `${group.group}${group.peak === 1 ? ' · 早高峰' : group.peak === 2 ? ' · 晚高峰' : ''}`,
    start: index, current: group.isNow === 1, times: group.times.filter(item => item.isDelete !== 1),
  })).filter(group => group.times.length)
  const periods = [{ name: '凌晨 · 00:00–05:59', start: 0, end: 6 }, { name: '上午 · 06:00–09:59', start: 6, end: 10 },
    { name: '白天 · 10:00–15:59', start: 10, end: 16 }, { name: '傍晚 · 16:00–19:59', start: 16, end: 20 }, { name: '夜间 · 20:00–23:59', start: 20, end: 24 }]
  return periods.map(period => ({ ...period, current: false, times: timetable.value?.times.filter(time => {
    const hour = Number(time.split(':')[0]); return hour >= period.start && hour < period.end
  }).map(time => ({ time, status: undefined, notes: '', noteText: '' })) || [] })).filter(period => period.times.length)
})
function busesForLine(line: LineSummary, buses: StationBus[]) { return buses.filter(bus => bus.name === line.name && bus.direction === line.direction) }
function visibleStationLines(station: Station, index: number) { return expandedStations.value.includes(stationKey(station)) ? station.lines : station.lines.slice(0, index === 0 ? 3 : 2) }
function toggleStationExpanded(station: Station) {
  const key = stationKey(station)
  expandedStations.value = expandedStations.value.includes(key) ? expandedStations.value.filter(item => item !== key) : [...expandedStations.value, key]
}

function stationKey(item: Station) { return `${item.number || item.name}:${item.lat}:${item.lng}` }
function clearHistory() { history.value = []; localStorage.removeItem('bus.history') }
function timeText(value: string) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '' }
function distanceText(value: number | null) { return value === null ? '距离未提供' : value >= 1000 ? `${(value / 1000).toFixed(1)} 公里` : `${Math.round(value)} 米` }
function directionText(direction: string) { return direction === '1' ? '上行' : '下行' }
function message(value: unknown) { return value instanceof Error ? value.message : String(value) }
function arrivalText(item: Arrival) {
  if (item.statusText) return item.statusText
  if (item.nextDeparture?.trim()) return `计划发车 ${item.nextDeparture.trim()}`
  if (item.waiting) return '等待发车'
  if (item.remainingStations === null) return '到站信息未提供'
  return item.remainingStations === 0 ? '剩余 0 站，请留意进站车辆' : `还有 ${item.remainingStations} 站`
}

function savePage() {
  if (restoring || !city.value || (view.value === 'route' && !route.value) || (view.value === 'station' && !selectedStation.value)) return
  const params = new URLSearchParams({ view: view.value, city: city.value.key })
  if (view.value === 'route' && route.value) {
    params.set('line', route.value.name)
    params.set('direction', route.value.direction)
    if (selectedOrder.value !== undefined) params.set('stop', String(selectedOrder.value))
    if (selectedRouteStation.value) params.set('stopName', selectedRouteStation.value.name)
    params.set('panel', routePanel.value)
  }
  if (view.value === 'station' && selectedStation.value) {
    params.set('station', selectedStation.value.name)
    if (selectedStation.value.number) params.set('number', selectedStation.value.number)
    params.set('lat', String(selectedStation.value.lat))
    params.set('lng', String(selectedStation.value.lng))
  }
  if (view.value === 'search' && searched.value) params.set('q', keyword.value)
  window.history.replaceState(null, '', `?${params}`)
}
watch([view, city, route, selectedStation, selectedOrder, routePanel, keyword, searched], savePage)

function navigate(next: typeof view.value, remember = true) {
  if (next === 'home') previousPages.value = []
  else if (remember && next !== view.value) {
    previousPages.value.push({ view: view.value, route: route.value, station: selectedStation.value, order: selectedOrder.value,
      keyword: keyword.value, results: searchResults.value, searched: searched.value, stopsError: stopsError.value, scroll: window.scrollY })
  }
  clearTimeout(timer)
  epoch++
  liveSequence++
  nearbySequence++
  searchSequence++
  timetableVisible.value = false
  stopDialog.value = false
  platformDialog.value = false
  refreshing.value = false
  nextDeparture.value = ''
  busy.value = false
  error.value = ''
  liveError.value = ''
  view.value = next
  if (next === 'home' && nearby.value.length) void refreshNearbyBuses()
  window.scrollTo({ top: 0, behavior: 'instant' })
}

async function goBack() {
  const previous = previousPages.value.pop()
  if (!previous) { navigate('home'); return }
  navigate(previous.view, false)
  const current = epoch
  route.value = previous.route
  selectedStation.value = previous.station
  selectedOrder.value = previous.order
  keyword.value = previous.keyword
  searchResults.value = previous.results
  searched.value = previous.searched
  stopsError.value = previous.stopsError
  vehicles.value = []; arrivals.value = []; stationBuses.value = []; liveTime.value = ''
  if (['route', 'station'].includes(previous.view)) await refreshLive()
  await nextTick()
  if (current !== epoch) return
  window.scrollTo({ top: previous.scroll, behavior: 'instant' })
}

async function action(work: () => Promise<void>) {
  const current = epoch
  busy.value = true
  error.value = ''
  try { await work() }
  catch (failure) { if (current === epoch) error.value = message(failure) }
  finally { if (current === epoch) busy.value = false }
}

function openCityDialog() {
  cityFilter.value = ''
  selectedProvince.value = ''
  cityDialog.value = true
}

function chooseCity(item: City) {
  locationSequence++
  city.value = item
  localStorage.setItem('bus.city', item.key)
  cityDialog.value = false
  position.value = undefined
  positionSequence++
  positionResults.value = []
  positionKeyword.value = ''
  positionSearched.value = false
  positionError.value = ''
  positionBusy.value = false
  nearby.value = []
  nearbyBuses.value = {}; nearbyErrors.value = {}; expandedStations.value = []
  selectedStation.value = undefined
  route.value = undefined
  locating.value = false
  locationError.value = ''
  locationStatus.value = '请选择查询位置，或使用当前位置识别城市'
  navigate('home')
}

async function loadNearby() {
  if (!city.value || !position.value) throw new Error('请先选择城市和查询位置')
  const currentCity = city.value.key
  const currentPosition = position.value
  const result = await api<Result<{ stations: Station[]; source: string }>>('nearby', { city: currentCity, lat: currentPosition.lat, lng: currentPosition.lng })
  if (city.value.key !== currentCity || position.value !== currentPosition) return
  nearby.value = result.data.stations
  nearbyTime.value = result.fetchedAt
  nearbyBuses.value = {}; nearbyErrors.value = {}; expandedStations.value = []
  if (view.value === 'home') void refreshNearbyBuses()
}

async function refreshNearbyBuses() {
  clearTimeout(timer)
  if (!city.value || view.value !== 'home') return
  const current = ++nearbySequence
  const currentCity = city.value!.key
  await Promise.all(nearby.value.slice(0, 3).filter(station => !isXiamen.value || station.number).map(async station => {
    const key = stationKey(station)
    try {
      const result = await api<Result<StationBus[]>>('station-buses', { city: currentCity, name: station.name, number: station.number || '', lat: station.lat, lng: station.lng })
      if (current !== nearbySequence || view.value !== 'home') return
      nearbyBuses.value[key] = result.data
      delete nearbyErrors.value[key]
    } catch (failure) { if (current === nearbySequence && view.value === 'home') nearbyErrors.value[key] = message(failure) }
  }))
  if (current === nearbySequence && view.value === 'home' && !document.hidden) timer = setTimeout(() => void refreshNearbyBuses(), 20000)
}

async function locate() {
  const current = ++locationSequence
  const currentEpoch = epoch
  locating.value = true
  locationError.value = ''
  pendingPosition.value = undefined
  locationStatus.value = '正在获取当前位置…'
  let cityResolved = false
  try {
    if (!window.isSecureContext) throw new Error('定位需要 HTTPS 或 localhost，请使用安全地址访问。')
    if (!navigator.geolocation) throw new Error('当前浏览器没有提供定位功能。')
    const result = await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }))
    if (current !== locationSequence) return
    const [gpsLng, gpsLat] = transform.wgs84togcj02(result.coords.longitude, result.coords.latitude)
    pendingPosition.value = { lat: gpsLat, lng: gpsLng, source: 'gps', accuracy: result.coords.accuracy }
    locationStatus.value = '正在识别城市…'
    // 此接口只接收浏览器本次授权取得的实际位置。
    const query = new URLSearchParams({ latitude: String(result.coords.latitude), longitude: String(result.coords.longitude), localityLanguage: 'zh' })
    const response = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?${query}`, { signal: AbortSignal.timeout(6000) })
    if (!response.ok) throw new Error(`城市识别服务返回 HTTP ${response.status}，请手动选择城市和位置。`)
    const address = await response.json()
    const names: string[] = [address.city, address.locality, ...(address.localityInfo?.administrative || []).map((item: { name: string }) => item.name)].filter(Boolean)
    const normalize = (name: string) => name.replace(/市$/, '')
    const matches = cities.value.filter(item => names.some(name => normalize(name) === normalize(item.name)))
    const detected = matches.find(item => normalize(item.name) === normalize(address.city || '')) || matches[0]
    if (!detected) throw new Error('定位城市未匹配公交城市配置，请手动选择城市和查询位置。')
    if (current !== locationSequence) return
    locatedCity.value = detected
    cityResolved = true
    if (currentEpoch !== epoch || view.value !== 'home') { locationStatus.value = '已取得定位城市'; return }
    const [lng, lat] = transform.wgs84togcj02(result.coords.longitude, result.coords.latitude)
    city.value = detected
    localStorage.setItem('bus.city', detected.key)
    position.value = { lat, lng, source: 'gps', accuracy: result.coords.accuracy }
    nearby.value = []
    navigate('home')
    locationStatus.value = `当前位置 · 定位精度约 ${Math.round(result.coords.accuracy)} 米`
    await loadNearby()
  } catch (failure) {
    if (current !== locationSequence) return
    const locationFailure = failure as GeolocationPositionError
    locationError.value = pendingPosition.value && !cityResolved ? '已取得位置，城市识别未完成。请确认查询城市，或重新定位。' : typeof locationFailure.code === 'number' ? ({ 1: '位置权限未获授权，可手动选择城市和查询位置。', 2: '设备暂时无法确定位置，可手动选择查询位置。', 3: '定位请求超时，可以重新定位或手动选择查询位置。' }[locationFailure.code] || message(failure)) : message(failure)
    locationStatus.value = pendingPosition.value ? '已取得位置，请确认查询城市' : '自动定位未完成'
  } finally { if (current === locationSequence) locating.value = false }
}

async function useLocatedPosition() {
  if (!pendingPosition.value) return
  locationSequence++
  locating.value = false
  position.value = pendingPosition.value
  locationError.value = ''
  locationStatus.value = `当前位置 · 定位精度约 ${Math.round(position.value.accuracy!)} 米`
  await action(loadNearby)
}

async function useManualPosition(lat = Number(manualLat.value), lng = Number(manualLng.value), name = '手动选择的位置') {
  if (!manualLat.value && !mapVisible.value && name === '手动选择的位置') throw new Error('请输入纬度')
  if (!manualLng.value && !mapVisible.value && name === '手动选择的位置') throw new Error('请输入经度')
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) throw new Error('请输入有效经纬度')
  locationSequence++
  locating.value = false
  position.value = { lat, lng, source: 'manual' }
  const currentPosition = position.value
  const current = positionSequence
  locationStatus.value = name
  nearby.value = []
  await loadNearby()
  if (position.value !== currentPosition || current !== positionSequence) return
  locationError.value = ''
  error.value = ''
  positionDialog.value = false
  mapVisible.value = false
  if (view.value === 'route') await refreshLive()
}

function openPositionDialog() {
  positionError.value = ''
  positionResults.value = []
  positionSearched.value = false
  coordinateVisible.value = false
  positionDialog.value = true
}

function closePositionDialog() {
  positionSequence++
  positionBusy.value = false
  positionDialog.value = false
  mapVisible.value = false
}

async function positionAction(work: () => Promise<void>) {
  const current = ++positionSequence
  positionBusy.value = true
  positionError.value = ''
  try { await work() }
  catch (failure) { if (current === positionSequence) positionError.value = message(failure) }
  finally { if (current === positionSequence) positionBusy.value = false }
}

async function searchPosition() {
  if (!positionKeyword.value.trim()) return
  await positionAction(async () => {
    const current = positionSequence
    const result = await api<Result<{ name: string }[]>>('search', { city: city.value!.key, keyword: positionKeyword.value.trim(), kind: 'station' })
    if (current !== positionSequence) return
    positionResults.value = result.data
    positionSearched.value = true
  })
}

async function useStationPosition(name: string) {
  await positionAction(async () => {
    const current = positionSequence
    const result = await api<Result<Station>>('station', { city: city.value!.key, name })
    if (current !== positionSequence) return
    await useManualPosition(result.data.lat, result.data.lng, `${result.data.name}附近`)
  })
}

function startSearch() {
  navigate('search')
  searchResults.value = { lines: [], stations: [] }
  searched.value = false
  nextTick(() => searchInput.value?.focus())
}

async function doSearch(value = keyword.value) {
  keyword.value = value.trim()
  if (!keyword.value) return
  const current = ++searchSequence
  const currentCity = city.value!.key
  searched.value = false
  searchResults.value = { lines: [], stations: [] }
  await action(async () => {
    const result = await api<Result<SearchResults>>('search', { city: currentCity, keyword: keyword.value, kind: 'all' })
    if (current !== searchSequence || currentCity !== city.value!.key) return
    searchResults.value = result.data
    searched.value = true
    history.value = [keyword.value, ...history.value.filter(item => item !== keyword.value)].slice(0, 8)
    localStorage.setItem('bus.history', JSON.stringify(history.value))
  })
}

async function openStation(item: Station | { name: string }) {
  navigate('station')
  selectedStation.value = undefined
  stationBuses.value = []
  liveTime.value = ''
  lineFilter.value = ''
  const current = epoch
  await action(async () => {
    let station: Station
    if ('lines' in item) {
      station = item
      if (!isXiamen.value || item.number) {
        const result = await api<Result<Station>>('station', { city: city.value!.key, name: item.name, number: item.number || '', lat: item.lat, lng: item.lng })
        station = { ...result.data, distance: item.distance, platformNumbers: item.platformNumbers }
      }
    }
    else {
      station = (await api<Result<Station>>('station', { city: city.value!.key, name: item.name })).data
    }
    if (current !== epoch) return
    selectedStation.value = station
    await refreshLive()
  })
}

async function selectPlatform(number: string) {
  const station = selectedStation.value!
  platformDialog.value = false
  await openStation({ ...station, number, distance: null })
}

async function selectNationalPlatform(station: Station) {
  platformDialog.value = false
  await openStation(station)
}

async function openLine(item: LineSummary, stopName?: string, order?: number) {
  navigate('route')
  route.value = undefined
  stopsError.value = ''
  selectedOrder.value = undefined
  vehicles.value = []
  arrivals.value = []
  liveTime.value = ''
  vehicleNotice.value = ''
  nextDeparture.value = ''
  timetable.value = undefined
  timetableVisible.value = false
  stopFilter.value = ''
  routePanel.value = 'diagram'
  const current = epoch
  await action(async () => {
    const result = await api<Result<Route>>('line', { city: city.value!.key, name: item.name, direction: item.direction })
    if (current !== epoch) return
    if (!result.data.stations.length) throw new Error('上游没有返回这个方向的站点列表。')
    route.value = result.data
    selectedOrder.value = result.data.stations.find(station => station.name === stopName && (!order || station.order === order))?.order || result.data.stations[0].order
    await refreshLive()
  })
}

async function switchDirection() {
  const line = route.value!
  const direction = line.direction === '1' ? '2' : '1'
  const stopName = selectedRouteStation.value?.name
  if (isXiamen.value) { await openLine({ name: line.name, direction, from: '', to: '' }, stopName); return }
  const current = epoch
  await action(async () => {
    const result = await api<Result<LineSummary[]>>('search', { city: city.value!.key, keyword: line.name, kind: 'line' })
    if (current !== epoch) return
    const reverse = result.data.find(item => item.name === line.name && item.direction === direction)
    if (!reverse) throw new Error('上游没有提供这条线路的另一方向。')
    await openLine(reverse, stopName)
  })
}

async function selectOrder(order: number) {
  stopDialog.value = false
  selectedOrder.value = order
  vehicles.value = []
  arrivals.value = []
  liveTime.value = ''
  nextDeparture.value = ''
  await refreshLive()
}

async function refreshLive() {
  clearTimeout(timer)
  const current = ++liveSequence
  const currentEpoch = epoch
  refreshing.value = true
  liveError.value = ''
  try {
    if (view.value === 'station') {
      const station = selectedStation.value
      if (!station || (isXiamen.value && !station.number)) return
      const result = await api<Result<StationBus[]>>('station-buses', { city: city.value!.key, name: station.name, number: station.number || '', lat: station.lat, lng: station.lng })
      if (current !== liveSequence || currentEpoch !== epoch) return
      stationBuses.value = result.data
      liveTime.value = result.fetchedAt
    } else if (view.value === 'route') {
      const line = route.value
      const station = selectedRouteStation.value
      if (!line || !station) return
      const lat = station?.lat ?? position.value?.lat
      const lng = station?.lng ?? position.value?.lng
      if (lat === undefined || lng === undefined) {
        liveError.value = '查询车辆需要查询位置。返回附近页面选择位置后，可以继续查询这条线路。'
        return
      }
      const result = await api<Result<{ vehicles: Vehicle[]; notice: string; arrivals?: Arrival[]; nextDeparture?: string }>>('vehicles', { city: city.value!.key, name: line.name, direction: line.direction, line_id: line.id || '', station_id: station.id, station_name: station.name, station_order: station.order, lat, lng })
      if (current !== liveSequence || currentEpoch !== epoch) return
      vehicles.value = result.data.vehicles
      vehicleNotice.value = result.data.notice
      nextDeparture.value = result.data.nextDeparture || ''
      liveTime.value = result.fetchedAt
      if (!isXiamen.value) arrivals.value = result.data.arrivals!
      if (isXiamen.value && station) {
        const arrival = await api<Result<Arrival[]>>('arrival', { city: city.value!.key, name: line.name, direction: line.direction, station_name: station.name, station_order: station.order })
        if (current === liveSequence && currentEpoch === epoch) arrivals.value = arrival.data
      }
    }
  } catch (failure) {
    if (current === liveSequence && currentEpoch === epoch) liveError.value = message(failure)
  } finally {
    if (current === liveSequence && currentEpoch === epoch) {
      refreshing.value = false
      if (!liveError.value && !document.hidden && (view.value === 'route' || (view.value === 'station' && selectedStation.value))) scheduleRefresh()
    }
  }
}

function scheduleRefresh() {
  clearTimeout(timer)
  timer = setTimeout(() => { if (!busy.value && !refreshing.value) void refreshLive(); else scheduleRefresh() }, 20000)
}

function connectionChanged() {
  if (!navigator.onLine) {
    clearTimeout(timer)
    liveSequence++
    nearbySequence++
    vehicles.value = []; arrivals.value = []; stationBuses.value = []; nearbyBuses.value = {}
    liveTime.value = ''; nextDeparture.value = ''; refreshing.value = false
    liveError.value = '当前离线，请联网后查询公交。'
    return
  }
  if (!city.value || restoring) { void initialize(); return }
  if (['route', 'station'].includes(view.value)) void refreshLive()
  else if (view.value === 'home' && position.value) void action(loadNearby)
}

function visibilityChanged() {
  clearTimeout(timer)
  if (!document.hidden && !refreshing.value && !busy.value && !liveError.value && ['station', 'route'].includes(view.value)) void refreshLive()
  if (!document.hidden && view.value === 'home' && nearby.value.length) void refreshNearbyBuses()
}

function toggleLineSaved() {
  const line = route.value!
  if (routeSaved.value) savedLines.value = savedLines.value.filter(item => !(item.city.key === city.value!.key && item.name === line.name && item.direction === line.direction))
  else savedLines.value.push({ city: city.value!, name: line.name, direction: line.direction, from: line.from || line.stations[0]?.name || '', to: line.to || line.stations.at(-1)?.name || '' })
  localStorage.setItem('bus.savedLines', JSON.stringify(savedLines.value))
}

function toggleStationSaved() {
  const station = selectedStation.value!
  if (stationSaved.value) savedStations.value = savedStations.value.filter(item => !(item.city.key === city.value!.key && stationKey(item.station) === stationKey(station)))
  else savedStations.value.push({ city: city.value!, station })
  localStorage.setItem('bus.savedStations', JSON.stringify(savedStations.value))
}

async function openSavedLine(item: SavedLine) { if (item.city.key !== city.value!.key) chooseCity(item.city); await openLine(item) }
async function openSavedStation(item: SavedStation) {
  if (item.city.key !== city.value!.key) chooseCity(item.city)
  await openStation(item.station)
}

async function loadTimetable() {
  const current = epoch
  await action(async () => {
    const line = route.value!
    const result = await api<Result<Timetable>>('timetable', { city: city.value!.key, name: line.name, line_id: line.id!, direction: line.direction })
    if (current === epoch) { timetable.value = result.data; timetableVisible.value = true }
  })
}

async function initialize() {
  const params = new URLSearchParams(window.location.search)
  await action(async () => {
    cities.value = await api<City[]>('cities')
    city.value = cities.value.find(item => item.key === (params.get('city') || localStorage.getItem('bus.city'))) || cities.value.find(item => item.code === '0592')!
  })
  if (!city.value) {
    if (!navigator.onLine) locationStatus.value = '当前离线'
    return
  }
  if (params.get('view') === 'route' && params.get('line') && ['1', '2'].includes(params.get('direction') || '')) {
    await openLine({ name: params.get('line')!, direction: params.get('direction')!, from: '', to: '' }, params.get('stopName') || undefined, params.has('stop') ? Number(params.get('stop')) : undefined)
    routePanel.value = params.get('panel') === 'vehicles' ? 'vehicles' : 'diagram'
  } else if (params.get('view') === 'search' && params.get('q')) {
    startSearch()
    await doSearch(params.get('q')!)
  } else if (params.get('view') === 'station' && params.get('station')) {
    await action(async () => {
      const result = await api<Result<Station>>('station', { city: city.value!.key, name: params.get('station')!, number: params.get('number') || '', lat: params.has('lat') ? Number(params.get('lat')) : undefined, lng: params.has('lng') ? Number(params.get('lng')) : undefined })
      await openStation(result.data)
    })
  } else if (params.get('view') === 'saved') navigate('saved')
  await nextTick()
  restoring = false
  savePage()
  if (view.value === 'home') void locate()
}
onMounted(() => {
  document.addEventListener('visibilitychange', visibilityChanged)
  window.addEventListener('offline', connectionChanged)
  window.addEventListener('online', connectionChanged)
  void initialize()
})
onUnmounted(() => { clearTimeout(timer); document.removeEventListener('visibilitychange', visibilityChanged); window.removeEventListener('offline', connectionChanged); window.removeEventListener('online', connectionChanged); locationSequence++; epoch++; liveSequence++; nearbySequence++ })
</script>

<template>
  <div class="app-shell">
    <header class="topbar" :class="{ 'query-topbar': view !== 'home' }">
      <button v-if="view === 'home'" class="brand" @click="navigate('home')" aria-label="返回附近站点"><span class="brand-icon"><BusFront :size="23" /></span><span>候车<span class="brand-caption">公交查询</span></span></button>
      <div v-if="view !== 'home'" class="page-bar"><button class="text-button" @click="goBack"><ArrowLeft :size="18" />{{ backLabel }}</button></div>
      <button v-if="view === 'home'" class="city-button" @click="openCityDialog" aria-label="切换城市"><MapPin :size="16" />{{ city?.name || '选择城市' }}<span>切换</span><ChevronDown :size="15" /></button>
    </header>
    <main>
      <div v-if="error" class="error banner" role="alert">{{ error }}<button @click="error = ''" aria-label="关闭提示"><X :size="17" /></button></div>
      <div v-if="busy" class="loading" role="status"><span class="loading-dot"></span>正在查询公交数据…</div>

      <template v-if="view === 'home'">
        <button class="search-box" @click="startSearch()"><Search :size="21" /><span>搜索线路、公交站名</span><kbd>查询</kbd></button>
        <section class="location-panel" :class="{ located: position }">
          <div><span class="location-pin"><LocateFixed :size="20" /></span><div><strong>{{ position ? (position.source === 'gps' ? '按当前位置查询' : '按所选位置查询') : locationStatus }}</strong></div></div>
          <div class="location-actions"><button class="text-button" :disabled="locating" @click="locate()"><LocateFixed :size="15" />{{ locating ? '正在定位' : '重新定位' }}</button><button class="text-button" @click="openPositionDialog"><Settings2 :size="15" />选择位置</button></div>
        </section>
        <p v-if="position?.source === 'gps'" class="hint">定位精度约 {{ Math.round(position.accuracy!) }} 米</p>
        <p v-if="locationError" class="error" role="alert">{{ locationError }}</p>
        <button v-if="pendingPosition && !position && !locating" class="text-button" @click="useLocatedPosition">确认在 {{ city?.name }}，使用已取得的位置查询</button>
        <div class="section-heading"><h2>附近站点<span v-if="nearby.length">{{ nearby.length }}</span></h2><button v-if="position" class="text-button" :disabled="busy" @click="action(loadNearby)"><RefreshCw :size="15" />刷新</button></div>
        <div v-if="nearest" class="nearby-grid">
          <article v-for="(station, index) in nearby" :key="stationKey(station)" class="station-card" :class="{ nearest: index === 0 }">
            <div class="station-heading"><div><h3>{{ station.name }}</h3><p>{{ distanceText(station.distance) }}<span v-if="station.platformNumbers?.length"> · {{ station.platformNumbers.length }} 个同名站台</span><span v-if="index === 0" class="nearest-label">{{ position?.source === 'gps' ? '离你最近' : '所选位置最近站点' }}</span></p></div><button class="round-button" @click="openStation(station)" :aria-label="`查询站点 ${station.name}`"><ChevronRight :size="19" /></button></div>
            <div v-if="station.lines.length" class="line-chips"><button v-for="line in visibleStationLines(station, index)" :key="`${line.name}-${line.direction}-${line.stationOrder}`" @click="openLine(line, station.name, line.stationOrder)"><span class="route-number">{{ line.name }}</span><span class="nearby-line-direction">开往 {{ line.to }}</span><span class="nearby-arrival" v-if="busesForLine(line, nearbyBuses[stationKey(station)] || []).length">{{ busesForLine(line, nearbyBuses[stationKey(station)] || [])[0]!.timeText || arrivalText(busesForLine(line, nearbyBuses[stationKey(station)] || [])[0]!) }}</span></button></div>
            <p v-if="nearbyErrors[stationKey(station)]" class="preview-error" role="status">到站查询失败：{{ nearbyErrors[stationKey(station)] }}</p>
            <div class="station-card-actions"><button v-if="station.lines.length > (index === 0 ? 3 : 2)" class="text-button" :aria-expanded="expandedStations.includes(stationKey(station))" @click="toggleStationExpanded(station)">{{ expandedStations.includes(stationKey(station)) ? '收起线路' : `全部 ${station.lines.length} 条线路` }}<ChevronDown :size="14" /></button><button class="card-link" @click="openStation(station)">站台与到站车辆<ArrowRight :size="15" /></button></div>
          </article>
        </div>
        <div v-else class="empty-panel"><MapPin :size="32" /><h3>{{ locating || busy ? '正在寻找附近站点' : position ? '附近暂无站点' : '选择查询位置' }}</h3><div class="empty-actions" v-if="!locating && !busy"><button class="primary" @click="openPositionDialog">选择查询位置</button><button class="text-button" @click="startSearch()">直接搜索线路<ArrowRight :size="16" /></button></div></div>
        <div class="update-note"><span v-if="nearbyTime">更新 {{ timeText(nearbyTime) }}</span><InfoTip label="定位与数据说明"><p>定位用于识别城市和查询附近站点。授权后，本次位置会提交给 BigDataCloud 和公交数据服务；用户定位坐标不会保存到浏览器收藏。</p><p>公交资料来自厦门公交与掌上公交 H5。前三个站点的到站资料每 20 秒更新，距离使用查询服务返回值。</p></InfoTip></div>
      </template>

      <template v-if="view === 'search'">
        <form class="search-form" @submit.prevent="doSearch()"><Search :size="20" /><input ref="searchInput" v-model="keyword" aria-label="线路或站点名称" :placeholder="`搜索${city?.name || ''}线路或站点`" /><button class="primary" :disabled="busy || !keyword.trim()">搜索</button></form>
        <div v-if="!searched && !busy && history.length" class="history"><h2>最近搜索</h2><button v-for="item in history" :key="item" @click="doSearch(item)"><Clock3 :size="14" />{{ item }}</button><button class="text-button" @click="clearHistory">清空记录</button></div>
        <div v-if="searched" class="search-columns">
          <section class="search-lines" aria-labelledby="search-lines-title"><h2 id="search-lines-title">线路 <span>{{ searchResults.lines.length }}</span></h2><div class="result-list"><button v-for="(item, index) in searchResults.lines" :key="`${item.name}-${index}`" class="result-row" @click="openLine(item)"><span class="route-number">{{ item.name }}</span><div><strong>开往 {{ item.to }}</strong><p>{{ item.from }} → {{ item.to }}</p></div><ChevronRight :size="19" /></button></div><p v-if="!searchResults.lines.length" class="hint">没有匹配的线路</p></section>
          <section class="search-stations" aria-labelledby="search-stations-title"><h2 id="search-stations-title">站点 <span>{{ searchResults.stations.length }}</span></h2><div class="result-list"><button v-for="(item, index) in searchResults.stations" :key="`${item.name}-${index}`" class="result-row" @click="openStation(item)"><MapPin :size="22" /><div><strong>{{ item.name }}</strong></div><ChevronRight :size="19" /></button></div><p v-if="!searchResults.stations.length" class="hint">没有匹配的站点</p></section>
        </div>
        <div v-if="searched && !searchResults.lines.length && !searchResults.stations.length" class="empty-panel"><Search :size="30" /><h3>没有找到匹配结果</h3><p>请检查城市和名称，使用完整线路名或站点名查询。</p></div>
      </template>

      <template v-if="view === 'station' && selectedStation">
        <div class="detail-heading"><div><h1>{{ selectedStation.name }}</h1><p v-if="selectedStation.distance !== null || selectedStation.number"><span v-if="selectedStation.distance !== null">{{ distanceText(selectedStation.distance) }}<span v-if="selectedStation.number"> · </span></span><span v-if="selectedStation.number">站台 {{ selectedStation.number }}</span></p></div><button class="save-button" :class="{ selected: stationSaved }" :aria-pressed="stationSaved" @click="toggleStationSaved" :aria-label="stationSaved ? '取消收藏站点' : '收藏站点'"><Heart :size="21" :fill="stationSaved ? 'currentColor' : 'none'" /><span>{{ stationSaved ? '已收藏' : '收藏' }}</span></button></div>
        <div v-if="otherPlatforms.length" class="platform-panel"><p>{{ selectedStation.platformNumbers?.length }} 个同名站台</p><button class="text-button" :disabled="busy" @click="otherPlatforms.length === 1 ? selectPlatform(otherPlatforms[0]!) : platformDialog = true"><RefreshCw :size="16" />{{ otherPlatforms.length === 1 ? '反向站台' : '切换站台' }}</button></div>
        <div v-if="nationalPlatforms.length" class="platform-panel"><p>{{ selectedStation.platforms?.length }} 个同名站台</p><button class="text-button" :disabled="busy" @click="platformDialog = true"><RefreshCw :size="16" />切换站台</button></div>
        <div class="section-heading"><h2>经过线路<span>{{ selectedStation.lines.length }}</span></h2><button class="text-button" :disabled="refreshing" @click="refreshLive"><RefreshCw :size="15" />{{ refreshing ? '正在刷新' : '刷新' }}</button></div>
        <label v-if="selectedStation.lines.length" class="field line-filter"><span class="sr-only">筛选线路或开往方向</span><input v-model="lineFilter" placeholder="筛选线路或开往方向" /></label>
        <div v-if="liveError" class="error" role="alert">{{ liveError }}</div>
        <div class="result-list"><button v-for="line in stationLines" :key="`${line.name}-${line.direction}-${line.stationOrder}`" class="result-row station-line" @click="openLine(line, selectedStation.name, line.stationOrder)"><span class="route-number">{{ line.name }}</span><div><strong>开往 {{ line.to }}</strong><p class="line-arrivals"><template v-if="busesForLine(line, stationBuses).length"><span v-for="(bus, index) in busesForLine(line, stationBuses).slice(0, 2)" :key="index">{{ arrivalText(bus) }}<span v-if="bus.timeText"> · {{ bus.timeText }}</span><span v-if="bus.distance !== null"> · {{ distanceText(bus.distance) }}</span></span></template><span v-else>{{ refreshing ? '正在查询到站车辆…' : '当前没有到站车辆资料' }}</span></p></div><ChevronRight :size="18" /></button></div>
        <div v-if="liveTime" class="update-note"><span>更新 {{ timeText(liveTime) }}</span><InfoTip label="站台到站说明"><p>到站资料每 20 秒更新。{{ liveError ? '查询失败后自动更新暂停，点击刷新重新查询。' : '' }}预计分钟由公交查询服务提供，受路况和调度影响。</p></InfoTip></div>
        <p v-if="lineFilter && !stationLines.length" class="hint">当前站台没有匹配的线路，请检查名称或切换站台。</p>
        <div v-if="!selectedStation.lines.length" class="empty-panel"><BusFront :size="30" /><h3>暂无经过线路</h3><button class="primary" @click="startSearch()">搜索线路</button></div>
      </template>

      <template v-if="view === 'route' && route">
        <section class="route-heading">
          <div class="route-top"><h1>{{ route.name }}</h1><div class="route-destination"><span>开往</span><h2>{{ route.to || route.stations.at(-1)?.name }}</h2></div><button class="switch-direction" :disabled="busy" @click="switchDirection" aria-label="切换方向"><RefreshCw :size="16" /><span>切换方向</span></button><button class="save-button" :class="{ selected: routeSaved }" :aria-pressed="routeSaved" @click="toggleLineSaved" :aria-label="routeSaved ? '取消收藏线路' : '收藏线路'"><Heart :size="19" :fill="routeSaved ? 'currentColor' : 'none'" /><span>{{ routeSaved ? '已收藏' : '收藏' }}</span></button></div>
          <div class="route-meta"><div class="route-basics"><div class="operating-times"><span v-if="route.first">首班 {{ route.first }}</span><span v-if="route.last">末班 {{ route.last }}</span><span v-if="route.stations.length">{{ route.stations.length }} 站</span></div><p v-if="route.fareDescription" class="route-fare">{{ route.fareDescription }}</p></div><button v-if="isXiamen || route.showTimetable" @click="loadTimetable"><Clock3 :size="14" />发车时刻表</button></div>
        </section>
        <div class="route-layout">
          <section class="route-live">
            <div class="boarding-heading"><div><span class="hint">乘车站</span><h2>{{ selectedRouteStation?.name }}</h2></div><button class="choose-stop" @click="stopFilter = ''; stopDialog = true" aria-label="选择乘车站"><MapPin :size="17" /><span>选择站点</span><ChevronDown :size="16" /></button></div>
            <p v-if="nextDeparture && !arrivals.some(item => item.nextDeparture === nextDeparture)" class="departure-note">起点预计发车 <strong>{{ nextDeparture }}</strong></p>
            <div class="arrival-strip"><div class="arrival-highlight" v-for="(item, index) in arrivals" :key="index"><strong>{{ item.timeText || arrivalText(item) }}</strong><p class="arrival-secondary"><span v-if="item.timeText && item.remainingStations !== null">{{ arrivalText(item) }}</span><span v-if="item.distanceText">{{ item.distanceText }}</span><span v-else-if="item.distance !== null">{{ distanceText(item.distance) }}</span><span v-if="item.nextDeparture">计划发车 {{ item.nextDeparture }}</span></p></div><p v-if="!arrivals.length" class="hint">{{ refreshing ? '正在查询到站资料…' : liveError ? '到站查询未完成，请刷新' : '当前没有到站车辆资料' }}</p></div>
            <div v-if="liveError" class="error" role="alert">{{ liveError }}</div>
            <div class="route-panel-bar"><div class="segmented" role="group" aria-label="线路显示内容"><button :class="{ active: routePanel === 'diagram' }" :aria-pressed="routePanel === 'diagram'" @click="routePanel = 'diagram'">站点图</button><button :class="{ active: routePanel === 'vehicles' }" :aria-pressed="routePanel === 'vehicles'" @click="routePanel = 'vehicles'">车辆列表 {{ vehicles.length }}</button></div><button class="text-button" :disabled="refreshing" @click="refreshLive" aria-label="刷新车辆"><RefreshCw :size="17" /><span>{{ refreshing ? '更新中' : '刷新' }}</span></button></div>
            <template v-if="routePanel === 'diagram'"><RouteDiagram v-if="route.stations.length" :stations="route.stations" :vehicles="vehicles" :selected="selectedOrder" :selectable="true" @select="selectOrder" /><p v-else class="hint">{{ stopsError || (busy ? '正在查询沿途站点…' : '当前方向没有站点资料') }}</p></template>
            <template v-else><article v-for="(vehicle, index) in vehicles" :key="`${vehicle.plate}-${index}`" class="vehicle-row"><span class="vehicle-icon"><BusFront :size="19" /></span><div><strong>{{ vehicle.plate }}</strong><p>{{ vehiclePosition(vehicle, route.stations) }}<span v-if="vehicle.order !== undefined && vehicle.order > selectedOrder!"> · 已驶过乘车站</span></p><p v-if="vehicle.distanceText">上游距离 {{ vehicle.distanceText }}</p><p v-if="vehicle.dataTime" class="source-note">位置时间 {{ timeText(vehicle.dataTime) }}</p></div></article><p v-if="!vehicles.length && !refreshing && !liveError" class="hint">当前没有返回车辆资料。</p></template>
            <div class="update-note"><span v-if="liveTime">更新 {{ timeText(liveTime) }}</span><InfoTip label="车辆与到站说明"><p>绿色车辆已到站，蓝色车辆位于两站之间。点击站名选择乘车站。图中的途中位置仅表示区间。</p><p>到站车辆按距离从近到远排列。车辆列表根据乘车站和车辆站序排列，已驶过车辆放在后面；同一区间缺少距站资料时保留上游顺序。未发车车辆显示等待或计划时间。</p><p>{{ vehicleNotice }}</p><p>预计到站分钟由掌上公交提供，受路况和调度影响。资料每 20 秒更新，车辆状态表示最后一次上报。{{ liveError ? '查询失败后自动更新暂停，点击刷新重新查询。' : '' }}</p></InfoTip></div>
          </section>
          <section class="route-stops"><p v-if="stopsError" class="error" role="alert">{{ stopsError }}</p><details class="all-stops"><summary>全部 {{ route.stations.length }} 个沿途站点</summary><p v-if="!route.stations.length && !busy && !stopsError" class="hint">上游没有返回这个方向的站点列表。</p><ol class="stop-list"><li v-for="station in route.stations" :key="station.order" :class="{ current: station.order === selectedOrder }"><button class="stop-item" @click="selectOrder(station.order)"><span class="stop-order">{{ station.order }}</span><span>{{ station.name }}<small v-if="station.order === selectedOrder">当前查询</small></span><span class="stop-vehicles" v-if="vehicles.some(vehicle => vehicle.order === station.order && vehicle.positionState === 'at-stop')"><BusFront :size="15" />{{ vehicles.filter(vehicle => vehicle.order === station.order && vehicle.positionState === 'at-stop').length }}</span></button></li></ol></details></section>
        </div>
      </template>

      <template v-if="view === 'saved'">
        <h1 class="page-title">我的收藏</h1>
        <div class="section-heading"><h2>收藏线路<span>{{ savedLines.length }}</span></h2></div>
        <div class="result-list"><button v-for="item in savedLines" :key="`${item.city.key}-${item.name}-${item.direction}`" class="result-row" @click="openSavedLine(item)"><span class="route-number">{{ item.name }}</span><div><strong>往 {{ item.to }}</strong><p>{{ item.city.name }} · {{ item.from }}</p></div><ChevronRight :size="18" /></button></div>
        <div class="section-heading"><h2>收藏站点<span>{{ savedStations.length }}</span></h2></div>
        <div class="result-list"><button v-for="item in savedStations" :key="`${item.city.key}-${stationKey(item.station)}`" class="result-row" @click="openSavedStation(item)"><MapPin :size="22" /><div><strong>{{ item.station.name }}</strong><p>{{ item.city.name }}<span v-if="item.station.number"> · {{ item.station.number }}</span></p></div><ChevronRight :size="18" /></button></div>
        <div v-if="!savedLines.length && !savedStations.length" class="empty-panel"><Heart :size="30" /><h3>暂无收藏</h3><button class="primary" @click="startSearch()">搜索线路</button><InfoTip label="收藏说明"><p>在线路或站点页面点击收藏。线路收藏会保留开往方向。</p></InfoTip></div>
      </template>
    </main>
    <PwaControls :show-install="view === 'home'" />
    <nav class="bottom-nav" aria-label="主导航"><button :class="{ active: view === 'home' }" @click="navigate('home')"><MapPin :size="21" /><span>附近</span></button><button :class="{ active: ['search', 'route', 'station'].includes(view) }" @click="startSearch()"><BusFront :size="22" /><span>查询</span></button><button :class="{ active: view === 'saved' }" @click="navigate('saved')"><Heart :size="21" /><span>收藏</span></button></nav>
  </div>

  <QueryDialog :open="cityDialog" labelledby="city-title" @close="cityDialog = false">
    <div class="section-heading"><h2 id="city-title">选择城市</h2><button class="round-button" @click="cityDialog = false" aria-label="关闭城市选择"><X :size="21" /></button></div>
    <button v-if="locatedCity" class="located-city" @click="chooseCity(locatedCity)"><LocateFixed :size="20" /><span>定位城市 <strong>{{ locatedCity.name }}</strong></span><span>选择</span></button>
    <label class="field">城市名称或拼音<input v-model="cityFilter" placeholder="例如：厦门 / xiamen" autofocus /></label>
    <div v-if="!cityFilter.trim()" class="city-browser">
      <div v-if="selectedProvince" class="province-path"><button class="text-button" @click="selectedProvince = ''" aria-label="返回省份"><ArrowLeft :size="16" />省份</button><strong>{{ selectedProvince }}</strong></div>
      <div v-else class="province-list" aria-label="省份"><button v-for="province in provinceOptions" :key="province" @click="selectedProvince = province">{{ province }}<ChevronRight :size="16" /></button></div>
    </div>
    <div v-if="cityFilter.trim() || selectedProvince" class="city-list"><button v-for="item in cityOptions" :key="item.key" @click="chooseCity(item)"><strong>{{ item.name }}</strong><span v-if="cityFilter.trim()">{{ item.province }}</span><ChevronRight :size="16" /></button><p v-if="!cityOptions.length" class="hint">没有匹配的城市</p></div>
    <InfoTip label="城市资料说明"><p>省份资料来自掌上公交城市配置。未提供省份的公开记录保留在其他地区。输入名称或拼音可直接查找城市，公交服务覆盖以查询结果为准。</p></InfoTip>
  </QueryDialog>
  <QueryDialog :open="positionDialog" labelledby="position-title" @close="closePositionDialog">
    <div class="section-heading"><h2 id="position-title">选择查询位置</h2><button class="round-button" @click="closePositionDialog" aria-label="关闭位置选择"><X :size="21" /></button></div>
    <div class="position-context"><span>{{ city?.name }}</span><InfoTip label="查询位置说明"><p>距离按所选站点或坐标计算。经纬度使用高德、腾讯地图的 GCJ02 坐标。</p></InfoTip></div>
      <form @submit.prevent="searchPosition"><label class="field">附近的公交站名<input v-model="positionKeyword" placeholder="输入你附近的公交站名" autofocus required /></label><button class="primary full-width" :disabled="positionBusy || !positionKeyword.trim()">查找公交站</button></form>
      <p v-if="positionSearched && !positionResults.length" class="hint">没有找到站点</p>
      <div class="position-results"><button v-for="item in positionResults" :key="item.name" :disabled="positionBusy" @click="useStationPosition(item.name)"><MapPin :size="18" /><span>{{ item.name }}</span><ChevronRight :size="18" /></button></div>
    <details class="data-details" :open="coordinateVisible" @toggle="coordinateVisible = ($event.target as HTMLDetailsElement).open"><summary>使用地图经纬度</summary>
      <form @submit.prevent="positionAction(() => useManualPosition())"><div class="coordinate-fields"><label class="field">纬度<input v-model="manualLat" inputmode="decimal" placeholder="例如 24.54" required /></label><label class="field">经度<input v-model="manualLng" inputmode="decimal" placeholder="例如 118.15" required /></label></div><button class="primary full-width" :disabled="positionBusy">查询这个位置附近的站点</button></form>
    </details>
    <button v-if="position && !mapVisible" class="text-button map-button" @click="mapVisible = true">打开地图选择位置</button>
    <StopMap v-if="mapVisible && position" :lat="position.lat" :lng="position.lng" :stations="nearby" @pick="(lat, lng) => positionAction(() => useManualPosition(lat, lng))" />
    <p v-if="positionBusy" class="loading" role="status">正在查询所选位置…</p><p v-if="positionError" class="error" role="alert">{{ positionError }}</p>
  </QueryDialog>
  <QueryDialog :open="stopDialog" labelledby="stop-title" @close="stopDialog = false">
    <div class="section-heading"><h2 id="stop-title">选择乘车站</h2><button class="round-button" @click="stopDialog = false" aria-label="关闭乘车站选择"><X :size="21" /></button></div>
    <p class="hint">{{ route?.name }} · 开往 {{ route?.to }}</p>
    <label class="field">筛选沿途站点<input v-model="stopFilter" placeholder="输入乘车站名称" autofocus /></label>
    <div class="stop-options"><button v-for="station in matchingStops" :key="station.order" :aria-pressed="station.order === selectedOrder" @click="selectOrder(station.order)"><span class="stop-order">{{ station.order }}</span><span>{{ station.name }}</span><small v-if="station.order === selectedOrder">当前查询</small></button></div>
    <p v-if="!matchingStops.length" class="hint">这个方向没有匹配站点，请检查站名或切换方向。</p>
  </QueryDialog>
  <QueryDialog :open="platformDialog" labelledby="platform-title" @close="platformDialog = false">
    <div class="section-heading"><h2 id="platform-title">选择同名站台</h2><button class="round-button" @click="platformDialog = false" aria-label="关闭站台选择"><X :size="21" /></button></div>
    <p class="hint">{{ selectedStation?.name }}</p>
    <div class="position-results"><button v-for="number in otherPlatforms" :key="number" @click="selectPlatform(number)"><MapPin :size="18" />站台 {{ number }}<ChevronRight :size="18" /></button></div>
    <div class="position-results"><button v-for="(station, index) in nationalPlatforms" :key="stationKey(station)" @click="selectNationalPlatform(station)"><MapPin :size="18" /><span>同名站台 {{ index + 1 }} · {{ station.lat.toFixed(5) }}, {{ station.lng.toFixed(5) }}</span><ChevronRight :size="18" /></button></div>
  </QueryDialog>
  <QueryDialog :open="timetableVisible && !!timetable" labelledby="timetable-title" @close="timetableVisible = false">
    <div class="section-heading"><h2 id="timetable-title">{{ route?.name }} 发车时刻表</h2><button class="round-button" @click="timetableVisible = false" aria-label="关闭时刻表"><X :size="21" /></button></div>
    <p class="hint">开往 {{ route?.to }}</p><p v-if="timetable?.nextDeparture" class="departure-note">下一班起点预计发车 <strong>{{ timetable.nextDeparture }}</strong></p><details v-for="group in timetableGroups" :key="group.start" class="timetable-period" :class="{ 'current-period': group.current }" open><summary>{{ group.name }}<span>{{ group.times.length }} 班</span></summary><div class="time-grid"><span v-for="(item, index) in group.times" :key="index" :class="{ 'past-time': item.status === 1, 'current-time': item.status === 2 }" :title="item.notes">{{ item.time }}<small v-if="item.noteText">{{ item.noteText }}</small></span></div><p v-for="(item, index) in group.times.filter(time => time.notes)" :key="index" class="hint">{{ item.time }}：{{ item.notes }}</p></details><InfoTip v-if="timetable?.tips" label="时刻表说明"><p>{{ timetable.tips }}</p></InfoTip><p v-if="!timetable?.times.length" class="hint">当前方向没有发车时刻资料。</p>
  </QueryDialog>
</template>
