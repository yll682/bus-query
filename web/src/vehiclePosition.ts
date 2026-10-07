import type { RouteStation, Vehicle } from './api'

export function vehiclePosition(vehicle: Vehicle, stations: RouteStation[]) {
  const index = stations.findIndex(station => station.order === vehicle.order)
  const target = stations[index]?.name
  if (!target) return '车辆所在站点未提供'
  if (vehicle.positionState === 'at-stop') return `已到 ${target}`
  if (vehicle.positionState === 'between') return index > 0 ? `${stations[index - 1].name} → ${target} 途中` : `正在驶向 ${target}`
  return `上报站点 ${target} · 进出站状态未提供`
}
