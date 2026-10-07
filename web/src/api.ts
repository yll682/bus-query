export interface City { key: string; name: string; code: string; province: string; pinyin: string }
export interface Position { lat: number; lng: number; source: 'gps' | 'manual'; accuracy?: number }
export interface LineSummary { name: string; direction: string; from: string; to: string; stationOrder?: number }
export interface Station {
  name: string; number: string | null; lat: number; lng: number; distance: number | null
  lines: LineSummary[]; coordinateSystem: string; platformNumbers?: string[]; platforms?: Station[]; sameNum?: number
}
export interface RouteStation { name: string; order: number; id?: string; lat?: number; lng?: number }
export interface Route {
  name: string; id: string | null; direction: string; stations: RouteStation[]
  from?: string; to?: string; first?: string; last?: string; source: string
  fareDescription?: string; showTimetable?: boolean
}
export interface Vehicle { plate: string; order?: number; positionState: 'at-stop' | 'between' | 'unknown'; nextStation?: string; currentStation?: string; dataTime?: string; distanceText?: string }
export interface SearchResults { lines: LineSummary[]; stations: { name: string }[] }
export interface Arrival { remainingStations: number | null; distance: number | null; nextDeparture: string | null; to: string; waiting?: boolean; statusText?: string; timeText?: string; distanceText?: string }
export interface StationBus extends Arrival { name: string; direction: string; plate?: string }
export interface Result<T> { data: T; fetchedAt: string }
export interface SavedLine extends LineSummary { city: City }
export interface SavedStation { station: Station; city: City }
export interface TimetableTime { time: string; status?: number; notes?: string; noteText?: string; isDelete?: number }
export interface Timetable {
  times: string[]; tips: string; nextDeparture?: string
  groups?: { group: string; peak: number; isNow: number; times: TimetableTime[] }[]
}

export async function api<T>(path: string, params: Record<string, string | number | undefined> = {}, signal?: AbortSignal): Promise<T> {
  if (!navigator.onLine) throw new Error('当前离线，请联网后查询公交。')
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined) query.set(key, String(value))
  const response = await fetch(`/api/${path}?${query}`, { signal })
  if (!response.ok) {
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error(`查询服务返回 HTTP ${response.status}，请检查服务运行状态。`)
    const result = await response.json()
    throw new Error(`${result.message || '查询失败'}${result.requestId ? `（查询编号 ${result.requestId.slice(0, 8)}）` : ''}`)
  }
  return response.json()
}
