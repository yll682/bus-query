import argparse
import base64
import hashlib
import json
import time
from urllib.parse import quote

import requests


NORMAL_PATHS = {
    "search", "lineDetail", "busList", "timeTable", "stationDetail",
    "nearestExactStation", "stationDetailBuses", "nearestBuses",
    "exactStationDetail", "exactStationDetailBuses", "busRemainingInfo",
    "transit", "busListInTransit",
}
V2_ORDER = {
    "lineBus": ("lineName", "upDown", "carNo"),
    "stationLineBus": ("stationNo", "stationName", "stationLon", "stationLat", "lineNum"),
    "transferBus": ("stationNames", "lineNames", "upDowns", "stationIndexs"),
    "transferDetailBus": ("stationNames", "lineNames", "upDowns", "stationIndexs"),
}
SNAPSHOT_PATHS = {"searchLinesOrStation", "getNearStation", "getBusInfo", "getBusRouteInfo"}
PUBLIC_COMMANDS = {
    "101": set(),
    "102": {"CITYNAME", "KEYWORD"},
    "103": {"CITYNAME", "LINENAME", "DIRECTION"},
    "104": {"CITYNAME", "LINENAME", "DIRECTION", "STATIONORDER"},
    "105": {"CITYNAME", "STATIONNAME", "MYLAT", "MYLNG"},
    "106": {"CITYNAME", "LAT", "LNG"},
    "110": {"CITYNAME", "KEYWORD"},
    "111": {"CITYNAME", "STARTPOINTNAME", "STARTPOINTLNG", "STARTPOINTLAT", "ENDPOINTNAME", "ENDPOINTLNG", "ENDPOINTLAT"},
    "112": {"CITYNAME", "REALLINE", "REALDIR", "STATIONORDER"},
    "113": {"CITYNAME", "REALLINE", "REALDIR", "STATIONORDER"},
    "114": {"CITYNAME", "KEYWORD"},
    "115": {"CITYNAME", "STATIONNAME", "MYLAT", "MYLNG", "ALL"},
    "116": {"CITYNAME", "ROUTEID", "DIRECTION"},
    "118": {"CITYNAME", "STARTPOINTNAME", "STARTPOINTLNG", "STARTPOINTLAT", "ENDPOINTNAME", "ENDPOINTLNG", "ENDPOINTLAT"},
    "119": {"CITYNAME", "KEY"},
    "120": {"CITYNAME", "LINELIST"},
    "203": {"CITYNAME"},
    "204": {"CITYNAME"},
    "205": {"CITYKEY"},
    "207": {"CITYNAME", "ROUTEID", "DIRECTION"},
    "209": {"CITYNAME", "STATIONNAME", "MYLAT", "MYLNG", "LAT", "LNG"},
}


class UpstreamError(ValueError):
    def __init__(self, path, code):
        super().__init__(f"{path}: 上游查询未成功，状态 {code}")
        self.path = path
        self.code = code


def normalize_params(params):
    return {
        key: ("" if value is None or value == "null" else str(value))
        .replace("<", "＜").replace(">", "＞")
        for key, value in params.items()
    }


def normal_sign(params, device_id, timestamp, token="", version="3.2.2"):
    params = normalize_params(params)
    salt = "e0hxlyguergtjpr6z7t1fck2mogvgcu9"
    source = (
        f"{salt}&app-version={version}"
        "&client-key=xmbus-app-01&client-id=1&client-type=android"
        f"&device-id={device_id}&timestamp={timestamp}&token={token}"
        f"&ticket-log=&{salt}"
    )
    source += "".join(f"&{key}={params[key]}" for key in sorted(params))
    digest = hashlib.md5(source.encode("utf-8")).hexdigest().upper()
    return base64.b64encode(digest.encode("ascii")).decode("ascii")


def v2_sign(path, params, timestamp):
    order = V2_ORDER[path]
    if set(params) != set(order):
        raise ValueError(f"{path} 参数集合要求 {order}")
    params = normalize_params(params)
    # 此顺序已通过四个 v2 接口的真实请求验证。
    source = "xmrbi202305" + "".join("&" + params[key] for key in order) + "&" + str(timestamp)
    digest = hashlib.md5(source.encode("utf-8")).hexdigest().upper()
    return hashlib.md5((digest + "&5F4E66A9FA0F11ED80C20CDA411D78A6").encode("ascii")).hexdigest().upper()


class XmbusClient:
    def __init__(self, device_id, token="", client_id=""):
        if not device_id:
            raise ValueError("device_id 不能为空")
        self.device_id = device_id
        self.token = token
        self.client_id = client_id
        self.session = requests.Session()

    def query(self, path, params):
        params = normalize_params(params)
        timestamp = str(int(time.time() * 1000))
        headers = {
            "client-id": "1", "client-type": "android", "client-key": "xmbus-app-01",
            "device-id": self.device_id, "timestamp": timestamp, "token": self.token,
            "appId": "xmrbi202305", "app-version": "3.2.2", "appVersion": "Android-v3.2.2",
            "clientId": self.client_id, "device-model": "Android", "area-code": "",
            "version": "v0.1", "ticket-log": "",
        }
        if path in V2_ORDER:
            url = "https://app.xmbus.com/xmbus/api/bus/v2/" + path
            headers["sign"] = v2_sign(path, params, timestamp)
            expected_code = 200
        elif path in NORMAL_PATHS:
            url = "https://app.xmbus.com/xmbus_web_app/bus/pub/routeQuery/" + path
            headers["sign"] = normal_sign(params, self.device_id, timestamp, self.token)
            expected_code = 0
        else:
            raise ValueError(f"未知接口 {path}")
        response = self.session.post(url, params=params, headers=headers, timeout=35)
        response.raise_for_status()
        result = response.json()
        if result.get("success") is False or result.get("code") != expected_code:
            raise UpstreamError(path, result.get("code"))
        return result


class ZsgjClient:
    def __init__(self):
        self.session = requests.Session()

    def public_query(self, command, params=None):
        command = str(command)
        if command not in PUBLIC_COMMANDS:
            raise ValueError(f"未知查询指令 {command}")
        params = {} if params is None else dict(params)
        required = PUBLIC_COMMANDS[command]
        optional = {"CITYKEY"}
        if command in {"112", "113"}:
            optional.add("STATIONNAME")
        if not required <= params.keys() or params.keys() - required - optional:
            raise ValueError(f"{command} 参数要求 {sorted(required)}，可选参数 {sorted(optional)}")
        if "CITYNAME" in required and not params["CITYNAME"]:
            raise ValueError("CITYNAME 不能为空")
        if "DIRECTION" in params and str(params["DIRECTION"]) not in {"1", "2"}:
            raise ValueError("DIRECTION 需要为 1 或 2")
        if command == "104" and (not str(params["STATIONORDER"]).isascii() or not str(params["STATIONORDER"]).isdigit() or int(params["STATIONORDER"]) < 1):
            raise ValueError("STATIONORDER 需要为正整数")
        if "ROUTEID" in params and (not str(params["ROUTEID"]).isascii() or not str(params["ROUTEID"]).isdigit() or int(params["ROUTEID"]) < 1):
            raise ValueError("ROUTEID 需要为正整数")
        response = self.session.post(
            "https://h5.mygolbs.com/ApiData.do",
            data={"CMD": command, **params},
            headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
                     "Accept": "application/json, text/javascript, */*; q=0.01",
                     "Origin": "https://h5.mygolbs.com", "Referer": "https://h5.mygolbs.com/"},
            timeout=35,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") not in {1, "1"}:
            raise UpstreamError("ApiData.do/CMD=" + command, result.get("status"))
        return result

    def public_cities(self):
        return self.public_query("101")

    def public_search(self, city_name, keyword, kind="all", city_key=""):
        if kind not in {"all", "line", "station"}:
            raise ValueError("kind 需要为 all、line 或 station")
        command = {"all": "102", "line": "114", "station": "110"}[kind]
        return self.public_query(command, {"CITYNAME": city_name, "KEYWORD": keyword, "CITYKEY": city_key})

    def public_lines(self, city_name, keyword="", city_key=""):
        return self.public_query("119", {"CITYNAME": city_name, "KEY": keyword, "CITYKEY": city_key})

    def public_line(self, city_name, line_name, direction, city_key=""):
        return self.public_query("103", {"CITYNAME": city_name, "LINENAME": line_name, "DIRECTION": direction, "CITYKEY": city_key})

    def public_nearby(self, city_name, lat, lng, city_key=""):
        return self.public_query("106", {"CITYNAME": city_name, "LAT": lat, "LNG": lng, "CITYKEY": city_key})

    def public_platforms(self, city_name, station_name, lat, lng, city_key=""):
        return self.public_query("209", {"CITYNAME": city_name, "STATIONNAME": station_name,
                                 "LAT": lat, "LNG": lng, "MYLAT": lat, "MYLNG": lng, "CITYKEY": city_key})

    def public_station_lines(self, city_name, station_name, lat, lng, all_lines=True, city_key=""):
        return self.public_query("115", {"CITYNAME": city_name, "STATIONNAME": station_name,
                                 "MYLAT": lat, "MYLNG": lng, "ALL": int(all_lines), "CITYKEY": city_key})

    def public_realtime(self, city_name, line_name, direction, station_order, city_key=""):
        return self.public_query("104", {"CITYNAME": city_name, "LINENAME": line_name,
                                 "DIRECTION": direction, "STATIONORDER": station_order, "CITYKEY": city_key})

    def public_timetable(self, city_name, route_id, direction):
        return self.public_query("207", {"CITYNAME": city_name, "ROUTEID": route_id,
                                 "DIRECTION": direction, "CITYKEY": ""})

    def public_transfer(self, city_name, start_name, start_lat, start_lng, end_name, end_lat, end_lng, city_key=""):
        return self.public_query("118", {"CITYNAME": city_name, "STARTPOINTNAME": start_name,
                                 "STARTPOINTLAT": start_lat, "STARTPOINTLNG": start_lng,
                                 "ENDPOINTNAME": end_name, "ENDPOINTLAT": end_lat,
                                 "ENDPOINTLNG": end_lng, "CITYKEY": city_key})

    def public_transfer_realtime(self, city_name, segments, detail=False, city_key=""):
        if not segments:
            raise ValueError("segments 不能为空")
        separator = "#" if detail else ","
        fields = {"REALLINE": "lineNames", "REALDIR": "dirs", "STATIONORDER": "orders", "STATIONNAME": "stations"}
        params = {key: separator.join(str(segment[field]) for segment in segments) for key, field in fields.items()}
        return self.public_query("113" if detail else "112", {"CITYNAME": city_name, "CITYKEY": city_key, **params})

    def public_notices(self, city_name, lines):
        return self.public_query("120", {"CITYNAME": city_name, "LINELIST": json.dumps(lines, ensure_ascii=False)})

    def public_arrival_analysis(self, city_name, city_code, line_name, direction, station_order):
        line = self.public_line(city_name, line_name, direction)
        if not any(int(station["stationOrder"]) == int(station_order) for station in line["data"]):
            raise ValueError("所选站序不在线路站点列表中")
        return self.arrive("Api", city_code, line["routeName"], line["upperOrDown"], line["routeId"], station_order)

    def featured_routes(self, city_code):
        if not city_code or any(char not in "0123456789_" for char in city_code):
            raise ValueError("城市编码需要保留配置中的数字和下划线")
        response = self.session.get("https://applet.mygolbs.com/featured-route/routes/" + city_code, timeout=35)
        response.raise_for_status()
        result = response.json()
        if result.get("success") is not True or result.get("code") not in {10000, 99999}:
            raise UpstreamError("featured-route/routes", result.get("code"))
        return result

    def snapshot(self, path, params):
        if path not in SNAPSHOT_PATHS:
            raise ValueError(f"未知接口 {path}")
        response = self.session.post(
            "https://snapshot.mygolbs.com/snapshot/" + path,
            json={**params, "serverTime": 152382832342},
            headers={"token": "zsgjxljc"}, timeout=35,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") != 200:
            raise UpstreamError(path, result.get("status"))
        return result

    def arrive(self, path, city_code, route_name, direction, route_id=None, station_order=None):
        if path not in {"getStation", "Api"}:
            raise ValueError(f"未知接口 {path}")
        # requests 编码 query 时会再次编码百分号。
        params = {"cityCode": city_code, "routeName": quote(route_name, safe=""), "direction": str(direction)}
        if path == "Api":
            if route_id is None or station_order is None:
                raise ValueError("Api 需要 route_id 和 station_order")
            params.update(routeId=str(route_id), staOrder=str(station_order))
        response = self.session.get("https://at.mygolbs.com:38886/ArriveTimes/" + path, params=params, timeout=35)
        response.raise_for_status()
        result = response.json()
        if result.get("status") not in {1, "1"}:
            raise UpstreamError(path, result.get("status"))
        return result


def verify_live(device_id):
    xm = XmbusClient(device_id)
    line = xm.query("lineDetail", {"busLineName": "91路"})["data"]
    assert line["id"] and line["stationList"], line
    bus = xm.query("lineBus", {"lineName": line["name"], "upDown": "1", "carNo": ""})
    assert isinstance(bus["data"], list), bus
    station = xm.query("stationLineBus", {"stationNo": "HL000111", "stationName": "高崎T4公交场站", "stationLon": "118.15230555", "stationLat": "24.54193506", "lineNum": "3"})
    transfer_params = {"stationNames": "航空产业园", "lineNames": "91路", "upDowns": "1", "stationIndexs": "3"}
    for path in ["transferBus", "transferDetailBus"]:
        assert isinstance(xm.query(path, transfer_params)["data"], list)
    zs = ZsgjClient()
    lines = zs.snapshot("searchLinesOrStation", {"cityName": "厦门市", "keyword": "91路", "searchType": "searchLine"})["data"]
    assert any(item["lineName"] == "91路" for item in lines), lines
    stations = zs.arrive("getStation", "0592", "91路", "1")["data"]
    assert stations and stations[0]["stationOrder"] == 1, stations
    arrival = zs.arrive("Api", "0592", "91路", "1", "161", "3")["data"]
    assert "at" in arrival and "title" in arrival, arrival
    print(json.dumps({"xmbus_line_id": line["id"], "v2_vehicles": len(bus["data"]), "v2_station_lines": len(station["data"]), "zsgj_stations": len(stations), "arrival_title": arrival["title"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--device-id", default="recovery-api-verification")
    args = parser.parse_args()
    if args.verify:
        verify_live(args.device_id)
    else:
        parser.print_help()
