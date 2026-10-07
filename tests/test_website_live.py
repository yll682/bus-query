import os

import requests
import pytest
from bus_api_client import XmbusClient, ZsgjClient
from website.service import arrival_key, vehicle_key


BASE = os.environ.get("BUS_TEST_URL", "http://127.0.0.1:8765")


def get(path, **params):
    response = requests.get(BASE + path, params=params, timeout=90)
    response.raise_for_status()
    return response.json()


@pytest.fixture(scope="module")
def cities():
    return get("/api/cities")


def test_health_and_page():
    assert get("/health")["status"] == "ok"
    assert get("/ready")["cities"] == 575
    response = requests.get(BASE, timeout=10)
    assert response.status_code == 200
    assert 'id="app"' in response.text
    assert response.headers["Permissions-Policy"] == "geolocation=(self)"


def test_city_records(cities):
    assert len(cities) == 575
    assert len({item["key"] for item in cities}) == 575
    assert any(item["name"] == "晋江市" and item["code"] == "" for item in cities)
    assert {item["name"] for item in cities if item["code"] == "0575_01"} == {"诸暨市", "嵊州市"}


def test_public_only_city_queries(cities):
    city = next(item for item in cities if item["name"] == "晋江市")
    assert not city["code"]
    lines = get("/api/search", city=city["key"], keyword="1路", kind="line")["data"]
    assert lines
    line = lines[0]
    route = get("/api/line", city=city["key"], name=line["name"], direction=line["direction"])["data"]
    assert route["id"] and route["stations"] and route["path"]


def test_xiamen_live(cities):
    city = next(item["key"] for item in cities if item["name"] == "厦门市")
    nearby = get("/api/nearby", city=city, lat=24.54193506, lng=118.15230555)["data"]["stations"]
    assert nearby and nearby[0]["name"] == "高崎T4公交场站"
    assert nearby[0]["distance"] == 0
    assert nearby[0]["number"] and nearby[0]["lines"]
    station = get("/api/station", city=city, name=nearby[0]["name"], number=nearby[0]["number"])["data"]
    assert station["number"] == nearby[0]["number"]
    assert station["lines"]
    buses = get("/api/station-buses", city=city, name=station["name"], number=station["number"], lat=station["lat"], lng=station["lng"])["data"]
    assert isinstance(buses, list)
    assert buses == sorted(buses, key=arrival_key)
    distances = [bus["distance"] for bus in buses if not bus["waiting"] and bus["distance"] is not None]
    assert distances == sorted(distances)
    for bus in buses:
        if bus["waiting"]:
            assert bus["distance"] is None and bus["remainingStations"] is None
    searches = get("/api/search", city=city, keyword="91路", kind="line")["data"]
    assert any(item["name"] == "91路" for item in searches)
    for direction in ["1", "2"]:
        route = get("/api/line", city=city, name="91路", direction=direction)["data"]
        assert route["stations"] and route["first"] and route["last"]
        stop = route["stations"][2]
        result = get("/api/vehicles", city=city, name=route["name"], direction=direction, line_id=route["id"], station_id=stop["id"], station_name=stop["name"], station_order=stop["order"], lat=stop["lat"], lng=stop["lng"])["data"]
        assert isinstance(result["vehicles"], list)
        assert result["vehicles"] == sorted(result["vehicles"], key=lambda item: vehicle_key(item, stop["order"]))
        for vehicle in result["vehicles"]:
            assert vehicle["positionState"] == {"0": "at-stop", "1": "between"}.get(str(vehicle["inOrOut"]), "unknown")
            if vehicle["reportedOrder"] is not None:
                assert vehicle["order"] == vehicle["reportedOrder"] + (vehicle["positionState"] == "between")
        arrival = get("/api/arrival", city=city, name=route["name"], direction=direction, station_name=stop["name"], station_order=stop["order"])["data"]
        assert isinstance(arrival, list)
        assert all("timeText" in item for item in arrival)
        table = get("/api/timetable", city=city, name=route["name"], direction=direction, line_id=route["id"])["data"]
        assert table["times"] and all(isinstance(item, str) for item in table["times"])


@pytest.mark.parametrize("name,keyword,lat,lng", [
    ("广州市", "1路", 23.1291, 113.2644),
    ("深圳市", "M113路", 22.5431, 114.0579),
    ("武汉市", "1路", 30.5928, 114.3055),
])
def test_national_live(cities, name, keyword, lat, lng):
    city = next(item["key"] for item in cities if item["name"] == name)
    nearby = get("/api/nearby", city=city, lat=lat, lng=lng)["data"]["stations"]
    assert nearby
    searches = get("/api/search", city=city, keyword=keyword, kind="line")["data"]
    assert searches
    line = searches[0]
    route = get("/api/line", city=city, name=line["name"], direction=line["direction"])["data"]
    assert route["stations"]
    assert route["id"] and route["path"]
    stop = route["stations"][min(5, len(route["stations"]) - 1)]
    station = get("/api/station", city=city, name=stop["name"], lat=stop["lat"], lng=stop["lng"])["data"]
    assert station["lines"] and station["platforms"]
    assert station["lat"] == pytest.approx(stop["lat"], abs=0.0001)
    buses = get("/api/station-buses", city=city, name=station["name"], lat=station["lat"], lng=station["lng"])["data"]
    assert buses and all("statusText" in item and "timeText" in item for item in buses)
    vehicles = get("/api/vehicles", city=city, name=line["name"], direction=line["direction"], station_order=stop["order"], lat=stop["lat"], lng=stop["lng"])["data"]
    assert isinstance(vehicles["vehicles"], list)
    assert vehicles["vehicles"] == sorted(vehicles["vehicles"], key=lambda item: vehicle_key(item, stop["order"]))
    approaching = [vehicle["order"] for vehicle in vehicles["vehicles"] if vehicle["positionState"] != "unknown" and vehicle["order"] <= stop["order"]]
    assert approaching == sorted(approaching, reverse=True)
    assert isinstance(vehicles["arrivals"], list)
    assert vehicles["arrivals"] == sorted(vehicles["arrivals"], key=arrival_key)
    distances = [item["distance"] for item in vehicles["arrivals"] if not item["waiting"] and item["distance"] is not None]
    assert distances == sorted(distances)
    assert vehicles["hasReal"] in {0, 1}
    table = get("/api/timetable", city=city, name=route["name"], direction=route["direction"], line_id=route["id"])["data"]
    assert isinstance(table["times"], list) and "groups" in table


@pytest.mark.parametrize("path,params", [
    ("/api/nearby", {"city": "0", "lat": 100, "lng": 118}),
    ("/api/nearby", {"city": "5000", "lat": 24, "lng": 118}),
    ("/api/search", {"city": "0", "keyword": "", "kind": "line"}),
    ("/api/line", {"city": "0", "name": "1路", "direction": "9"}),
    ("/api/station", {"city": "0", "name": "公园前", "lat": 23}),
])
def test_input_validation(path, params):
    response = requests.get(BASE + path, params=params, timeout=10)
    assert response.status_code == 422
    assert response.json()["message"]


def test_shenzhen_route_and_selected_stop(cities):
    city = next(item["key"] for item in cities if item["name"] == "深圳市")
    response = requests.get(BASE + "/api/line", params={"city": city, "name": "M200路", "direction": "1"}, timeout=90)
    assert response.status_code == 200, response.text
    route = response.json()["data"]
    assert route["stations"] and route["id"]
    stop = route["stations"][2]
    result = get("/api/vehicles", city=city, name="M200路", direction="1", station_order=stop["order"], lat=stop["lat"], lng=stop["lng"])["data"]
    assert isinstance(result["vehicles"], list)
    response = requests.get(BASE + "/api/vehicles", params={"city": city, "name": "M200路", "direction": "1", "lat": stop["lat"], "lng": stop["lng"]}, timeout=10)
    assert response.status_code == 422


@pytest.mark.parametrize("city_name,keyword", [("厦门市", "高崎"), ("广州市", "公园前")])
def test_combined_search(cities, city_name, keyword):
    city = next(item["key"] for item in cities if item["name"] == city_name)
    result = get("/api/search", city=city, keyword=keyword, kind="all")["data"]
    assert result["stations"]
    assert result["lines"] == get("/api/search", city=city, keyword=keyword, kind="line")["data"]
    assert result["stations"] == get("/api/search", city=city, keyword=keyword, kind="station")["data"]


@pytest.mark.parametrize("city_name,line_name,direction", [("厦门市", "91路", "1"), ("厦门市", "91路", "2"), ("广州市", "1路", "1")])
def test_fare_description_from_source(cities, city_name, line_name, direction):
    city = next(item for item in cities if item["name"] == city_name)
    route = get("/api/line", city=city["key"], name=line_name, direction=direction)["data"]
    client = XmbusClient("bus-web-local") if city["code"] == "0592" else ZsgjClient()
    try:
        if city["code"] == "0592":
            fare = client.query("lineDetail", {"busLineName": line_name})["data"]["comments"]
        else:
            fare = client.public_line(city_name, line_name, direction)["commonts"]
    finally:
        client.session.close()
    assert fare and route["fareDescription"] == fare


@pytest.mark.parametrize("city_name,line_name", [("厦门市", "91路"), ("广州市", "1路")])
def test_first_stop_waiting_and_arrival_order(cities, city_name, line_name):
    city = next(item["key"] for item in cities if item["name"] == city_name)
    route = get("/api/line", city=city, name=line_name, direction="1")["data"]
    stop = route["stations"][0]
    records = get("/api/arrival", city=city, name=line_name, direction="1", station_name=stop["name"], station_order=stop["order"])["data"]
    assert isinstance(records, list)
    assert records == sorted(records, key=arrival_key)
    for record in records:
        if record["waiting"]:
            assert record["distance"] is None
            assert record["remainingStations"] is None
            assert record["distanceText"] == ""
        else:
            assert record["plate"] and record["remainingStations"] >= 0


def test_pwa_public_files():
    response = requests.get(BASE + "/manifest.webmanifest", timeout=10)
    response.raise_for_status()
    assert "application/manifest+json" in response.headers["Content-Type"]
    assert response.headers["Cache-Control"] == "no-cache"
    manifest = response.json()
    assert manifest["id"] == "/" and manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])
    for path in ["/sw.js", "/apple-touch-icon-180x180.png", "/favicon.ico", *[icon["src"] for icon in manifest["icons"]]]:
        asset = requests.get(BASE + path, timeout=10)
        asset.raise_for_status()
        assert asset.content
        if path == "/sw.js":
            assert "javascript" in asset.headers["Content-Type"]
            assert asset.headers["Cache-Control"] == "no-cache"
    assert requests.get(BASE + "/not-a-public-file", timeout=10).status_code == 404
