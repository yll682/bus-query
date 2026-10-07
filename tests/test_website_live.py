import os

import requests
import pytest


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
    searches = get("/api/search", city=city, keyword="91路", kind="line")["data"]
    assert any(item["name"] == "91路" for item in searches)
    for direction in ["1", "2"]:
        route = get("/api/line", city=city, name="91路", direction=direction)["data"]
        assert route["stations"] and route["first"] and route["last"]
        stop = route["stations"][2]
        result = get("/api/vehicles", city=city, name=route["name"], direction=direction, line_id=route["id"], station_id=stop["id"], station_name=stop["name"], station_order=stop["order"], lat=stop["lat"], lng=stop["lng"])["data"]
        assert isinstance(result["vehicles"], list)
        arrival = get("/api/arrival", city=city, name=route["name"], direction=direction, station_name=stop["name"], station_order=stop["order"])["data"]
        assert isinstance(arrival, list)
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
    assert isinstance(vehicles["arrivals"], list)
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
