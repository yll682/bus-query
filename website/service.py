import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from cachetools import TTLCache

from bus_api_client import XmbusClient, ZsgjClient


ROOT = Path(__file__).resolve().parent.parent
DEVICE_ID = os.environ.get("BUS_DEVICE_ID", "bus-web-local")
if not DEVICE_ID:
    raise ValueError("BUS_DEVICE_ID 不能为空")
CITY_DATA = json.loads((ROOT / "掌上公交城市配置.json").read_text(encoding="utf-8"))
CITIES = [
    {"key": str(index), "name": item["cityname"], "code": item["citycode"],
     "province": item["province"], "pinyin": item.get("citynamepy", "")}
    for index, item in enumerate(CITY_DATA)
]
PUBLIC_CITIES = json.loads((ROOT / "掌上公交公开城市列表.json").read_text(encoding="utf-8"))["data"]
configured_names = {item["name"] for item in CITIES}
for item in PUBLIC_CITIES:
    if item["cityname"] not in configured_names:
        CITIES.append({"key": str(len(CITIES)), "name": item["cityname"], "code": "", "province": "", "pinyin": ""})
        configured_names.add(item["cityname"])
CACHE = TTLCache(maxsize=512, ttl=15)
LOCK = RLock()


class QueryError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def city_for(key):
    if not key.isdigit() or not 0 <= int(key) < len(CITIES):
        raise QueryError("城市编号无效", 422)
    return CITIES[int(key)]


def cached(key, query):
    with LOCK:
        if key in CACHE:
            return CACHE[key]
    result = {"data": query(), "fetchedAt": datetime.now(timezone.utc).isoformat()}
    with LOCK:
        CACHE[key] = result
    return result


@contextmanager
def client_for(city):
    client = XmbusClient(DEVICE_ID) if city["code"] == "0592" else ZsgjClient()
    with client_resource(client):
        yield client


@contextmanager
def client_resource(client):
    try:
        yield client
    finally:
        client.session.close()


def line_item(item):
    direction = str(item["upperOrDownInLine"])
    return {"name": item["lineName"], "direction": direction,
            "from": item["suStation"] if direction == "1" else item["sdStation"],
            "to": item["euStation"] if direction == "1" else item["edStation"],
            "stationOrder": item["stationOrderInLine"]}


def native_station(item):
    return {"name": item["name"], "number": item.get("stationNo"),
            "lat": float(item["gcjLat"]), "lng": float(item["gcjLng"]),
            "distance": item.get("distance"), "coordinateSystem": "GCJ02",
            "platformNumbers": item.get("relativeStationNoList") or [],
            "lines": [line_item(line) for line in item.get("lineList") or []]}


def public_line_item(item):
    return {"name": item["lineName"], "direction": str(item["upperOrDown"]),
            "from": item["from"], "to": item["to"], "stationOrder": item["stationOrder"]}


def public_station(item):
    return {"name": item["name"], "number": None, "lat": float(item["lat"]),
            "lng": float(item["lon"]), "distance": item["dis"] if item["dis"] >= 0 else None,
            "coordinateSystem": "unconfirmed", "lines": [], "sameNum": item["sameNum"]}


def public_station_bus(item):
    return {"name": item["lineName"], "direction": str(item["upperOrDown"]), "to": item["to"],
            "remainingStations": None, "distance": None, "nextDeparture": None,
            "statusText": item["neartext"], "timeText": item["neardis"], "stationOrder": item["stationOrder"]}


def public_arrivals(raw):
    return [{"remainingStations": item["busToStationCount"] if item["busToStationCount"] >= 0 else None,
             "distance": item["busToStationDistance"] if item["busNumber"] else None,
             "nextDeparture": item["planTime"] if not item["busNumber"] else None,
             "to": item["toStationName"], "plate": item["busNumber"],
             "statusText": item["busToStationTips"], "timeText": item["busToStationTimeTips"],
             "distanceText": item["busToStationDistanceTips"]} for item in raw["routeOnStationRTimeInfoList"]]


def nearby(city, lat, lng):
    def query():
        with client_for(city) as client:
            if city["code"] == "0592":
                raw = client.query("nearestExactStation", {"lat": lat, "lng": lng, "num": 8})["data"]
                stations = [native_station(item) for item in raw]
            else:
                raw = client.public_nearby(city["name"], lat, lng)["data"]
                stations = [public_station(item) for item in raw]
                for station in stations[:3]:
                    lines = client.public_station_lines(city["name"], station["name"], station["lat"], station["lng"])["data"]
                    station["lines"] = [public_line_item(line) for line in lines]
            return {"stations": sorted(stations, key=lambda item: (item["distance"] is None, item["distance"])),
                    "source": "厦门公交" if city["code"] == "0592" else "掌上公交 H5"}
    return cached(("near", city["key"], lat, lng), query)


def search(city, keyword, kind):
    def query():
        with client_resource(ZsgjClient()) as client:
            if city["code"] != "0592":
                raw = client.public_search(city["name"], keyword, kind)
                return [{"name": item["lineName"], "direction": str(item["upperOrDown"]),
                         "from": item["from"], "to": item["to"]} for item in raw["buslines"]] if kind == "line" else [{"name": item["stationName"]} for item in raw["busstations"]]
            raw = client.snapshot("searchLinesOrStation", {"cityName": city["name"],
                                  "keyword": keyword, "searchType": "searchLine" if kind == "line" else "searchStation"})["data"]
            return [{"name": item["lineName"], "direction": str(item["direction"]),
                     "from": item["from"], "to": item["to"]} for item in raw] if kind == "line" else [{"name": item["stationName"]} for item in raw]
    return cached(("search", city["key"], keyword, kind), query)


def station_detail(city, name, number, lat=None, lng=None):
    def query():
        with client_for(city) as client:
            if city["code"] != "0592":
                platforms = client.public_platforms(city["name"], name, "" if lat is None else lat, "" if lng is None else lng)["info"]
                if not platforms:
                    raise QueryError("上游没有返回这个站点的资料", 404)
                selected = min(platforms, key=lambda item: (float(item["lat"]) - lat) ** 2 + (float(item["lon"]) - lng) ** 2) if lat is not None else platforms[0]
                station = public_station(selected)
                station["platforms"] = [public_station(item) for item in platforms]
                lines = client.public_station_lines(city["name"], station["name"], station["lat"], station["lng"])["data"]
                station["lines"] = [public_line_item(line) for line in lines]
                return station
            params = {"stationNo": number, "reverseStationNo": "", "amapStationId": ""}
            raw = client.query("exactStationDetail", params)["data"] if number else client.query("stationDetail", {"busStationName": name})["data"]
            if not raw:
                raise QueryError("上游没有返回这个站点的资料", 404)
            station = native_station(raw)
            if number:
                station["number"] = number
            return station
    return cached(("station", city["key"], name, number, lat, lng), query)


def station_buses(city, name, number, lat, lng):
    if city["code"] == "0592" and not number:
        raise QueryError("这个站点尚未取得实时车辆接口", 422)
    def query():
        with client_for(city) as client:
            if city["code"] != "0592":
                raw = client.public_station_lines(city["name"], name, lat, lng)["data"]
                return [public_station_bus(item) for item in raw]
            raw = client.query("stationLineBus", {"stationNo": number, "stationName": name,
                                "stationLon": lng, "stationLat": lat, "lineNum": "20"})["data"]
            return [{"name": item["lineName"], "direction": str(item["upDown"]),
                     "to": item["endStationName"], "plate": item.get("carNo"),
                     "remainingStations": item.get("remainNum"), "distance": item.get("remainDist"),
                     "nextDeparture": item.get("nextTime")} for item in raw]
    return cached(("station-buses", city["key"], name, number, lat, lng), query)


def line_detail(city, name, direction):
    def query():
        with client_for(city) as client:
            if city["code"] == "0592":
                raw = client.query("lineDetail", {"busLineName": name})["data"]
                if not raw:
                    raise QueryError("上游没有返回这条线路的资料", 404)
                prefix = "u" if direction == "1" else "d"
                stations = [{"name": item["name"], "order": item["stationOrder"],
                             "id": item["id"], "lat": float(item["gcjLat"]),
                             "lng": float(item["gcjLng"])} for item in raw["stationList"] if str(item["upperOrDown"]) == direction]
                return {"name": raw["name"], "id": raw["id"], "direction": direction,
                        "from": raw["s" + prefix + "Station"], "to": raw["e" + prefix + "Station"],
                        "first": raw["s" + prefix + "Time"], "last": raw["e" + prefix + "Time"],
                        "price": raw.get("basicPrice"), "stations": sorted(stations, key=lambda item: item["order"]),
                        "source": "厦门公交", "coordinateSystem": "GCJ02"}
            raw = client.public_line(city["name"], name, direction)
            stations = [{"name": item["stationName"], "order": item["stationOrder"],
                         "lat": item["station_lat"], "lng": item["station_lon"]} for item in raw["data"]]
            return {"name": raw["routeName"], "id": str(raw["routeId"]), "direction": str(raw["upperOrDown"]),
                    "from": stations[0]["name"] if stations else "", "to": stations[-1]["name"] if stations else "",
                    "first": raw["firstLast"][0]["first"] if raw["firstLast"] else "",
                    "last": raw["firstLast"][0]["last"] if raw["firstLast"] else "",
                    "operatingPeriods": raw["firstLast"], "fareDescription": raw["commonts"],
                    "showTimetable": raw["showDepart"] == 1, "path": raw["nihelist"],
                    "companies": raw["companys"], "relatedRoutes": raw["StationRelatedRouteName"],
                    "stations": sorted(stations, key=lambda item: item["order"]),
                    "source": "掌上公交 H5", "coordinateSystem": "unconfirmed"}
    return cached(("line", city["key"], name, direction), query)


def vehicles(city, name, direction, line_id, station_id, station_name, station_order, lat, lng):
    def query():
        with client_for(city) as client:
            if city["code"] == "0592":
                if not line_id or not station_id or not station_order:
                    raise QueryError("厦门车辆查询需要线路和所选站点编号", 422)
                raw = client.query("busList", {"busLineId": line_id, "direction": direction,
                                   "stationSeq": station_order, "stationId": station_id,
                                   "stationName": station_name})["data"]
                return {"vehicles": [{"plate": item["plateNo"], "order": item.get("stationOrder"),
                        "nextStation": item.get("nextStationName"), "dataTime": item.get("dataTime"),
                        "lat": item.get("lat"), "lng": item.get("lng")} for item in raw],
                        "notice": "车辆位置来自上游，站点序号依据厦门公交返回值。"}
            if not station_order:
                raise QueryError("车辆查询需要选择乘车站", 422)
            raw = client.public_realtime(city["name"], name, direction, station_order)
            return {"vehicles": [{"plate": item["busNumber"], "order": item["index"] + 1,
                                  "currentStation": item["stationName"], "lat": item["bus_lat"], "lng": item["bus_lng"],
                                  "statusType": item["statusType"],
                                  "dataTime": datetime.fromtimestamp(item["_recTime"] / 1000, timezone.utc).isoformat()}
                                 for item in raw.get("list", [])],
                    "arrivals": public_arrivals(raw), "hasReal": raw["hasReal"], "runState": raw["runState"],
                    "nextDeparture": raw.get("planTime"), "segments": raw.get("speedlist"),
                    "notice": "这条线路未开通实时数据查询。" if raw["hasReal"] == 0 else "这条线路已停运。" if raw["runState"] == 1 else "到站站数、时间及距离由掌上公交提供，请提前候车。"}
    return cached(("vehicles", city["key"], name, direction, line_id, station_id, station_order, lat, lng), query)


def arrival(city, name, direction, station_name, station_order):
    def query():
        with client_for(city) as client:
            if city["code"] != "0592":
                raw = client.public_realtime(city["name"], name, direction, station_order)
                return public_arrivals(raw)
            raw = client.query("transferDetailBus", {"stationNames": station_name, "lineNames": name,
                               "upDowns": direction, "stationIndexs": station_order})["data"]
            return [{"remainingStations": item.get("remainNum"), "distance": item.get("remainDist"),
                     "nextDeparture": item.get("nextTime"), "to": item.get("endStationName")} for item in raw]
    return cached(("arrival", city["key"], name, direction, station_name, station_order), query)


def timetable(city, name, line_id, direction):
    def query():
        with client_for(city) as client:
            if city["code"] != "0592":
                raw = client.public_timetable(city["name"], line_id, direction)
                return {"times": [item["time"] for group in raw["list"] for item in group["times"] if item["isDelete"] != 1],
                        "groups": raw["list"], "nextDeparture": raw["nextTime"], "special": raw["special"],
                        "tips": "计划发车时间可能临时调整，请提前候车。" if raw["special"] == "1" and city["name"] != "泉州市" else "时刻表根据历史数据计算，仅供参考，请提前候车。"}
            raw = client.query("timeTable", {"busLineId": line_id, "busLineName": name})["data"]
            return {"times": [item["time"] for item in raw["upPlan" if direction == "1" else "downPlan"]], "tips": raw["tips"]}
    return cached(("timetable", city["key"], line_id, direction), query)
