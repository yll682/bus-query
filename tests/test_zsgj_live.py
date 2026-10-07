import pytest

from bus_api_client import ZsgjClient


@pytest.fixture(scope="module")
def client():
    value = ZsgjClient()
    yield value
    value.session.close()


def test_public_city_list(client):
    cities = client.public_cities()["data"]
    assert len(cities) >= 500
    assert {"厦门市", "广州市", "泉州市", "北京市"} <= {city["cityname"] for city in cities}


@pytest.mark.parametrize("city,name", [
    ("厦门市", "91路"), ("广州市", "1路"), ("深圳市", "M113路"),
    ("武汉市", "1路"), ("福州市", "1路"), ("泉州市", "1路"),
    ("北京市", "1路"), ("上海市", "01路"), ("杭州市", "1路"),
    ("南京市", "1路"), ("成都市", "1路"),
])
def test_public_city_queries(client, city, name):
    lines = client.public_search(city, name, "line")["buslines"]
    assert any(line["lineName"] == name for line in lines)
    route = client.public_line(city, name, "1")
    assert route["routeName"] == name and route["routeId"] > 0
    assert route["data"] and route["nihelist"] and route["firstLast"]
    assert all(-90 <= station["station_lat"] <= 90 and -180 <= station["station_lon"] <= 180 for station in route["data"])
    assert [station["stationOrder"] for station in route["data"]] == list(range(1, len(route["data"]) + 1))
    station = route["data"][5]
    realtime = client.public_realtime(city, name, "1", station["stationOrder"])
    assert realtime["hasReal"] in {0, 1}
    assert isinstance(realtime["routeOnStationRTimeInfoList"], list)
    for bus in realtime.get("list", []):
        assert bus["busNumber"] and 0 <= bus["index"] < len(route["data"])
        assert -90 <= bus["bus_lat"] <= 90 and -180 <= bus["bus_lng"] <= 180
        assert bus["_recTime"] > 0
    for tip in realtime["routeOnStationRTimeInfoList"]:
        assert tip["routeName"] == name
        assert int(tip["stationIndex"]) + 1 == station["stationOrder"]
    timetable = client.public_timetable(city, route["routeId"], "1")
    assert isinstance(timetable["list"], list)
    assert timetable["special"] in {"0", "1"}
    nearby = client.public_nearby(city, station["station_lat"], station["station_lon"])["data"]
    assert nearby and nearby[0]["dis"] == 0
    platforms = client.public_platforms(city, station["stationName"], station["station_lat"], station["station_lon"])["info"]
    assert platforms
    station_lines = client.public_station_lines(city, station["stationName"], station["station_lat"], station["station_lon"])["data"]
    assert station_lines and all(line["lineName"] and line["upperOrDown"] for line in station_lines)


def test_public_route_directory(client):
    result = client.public_lines("厦门市")
    assert len(result["buslines"]) > 100
    assert any(line["lineName"] == "91路" for line in result["buslines"])
    stations = client.public_search("厦门市", "高崎", "station")["busstations"]
    assert stations and all(station["stationName"] for station in stations)
    assert "busstations" in client.public_search("厦门市", "91路")


def test_public_transfer_queries(client):
    route = client.public_line("厦门市", "91路", "2")
    start, end = route["data"][2], route["data"][-3]
    result = client.public_transfer("厦门市", start["stationName"], start["station_lat"], start["station_lon"], end["stationName"], end["station_lat"], end["station_lon"])
    assert result["info"]
    segments = result["info"][0]["lines"]
    assert segments
    assert client.public_transfer_realtime("厦门市", [segments[0]])["data"]
    assert client.public_transfer_realtime("厦门市", segments, detail=True)["data"]


def test_public_analysis_route_id(client):
    result = client.public_arrival_analysis("广州市", "020", "1路", "1", 6)
    assert result["status"] == 1 and result["data"]["title"]


def test_other_public_commands(client):
    route = client.public_line("厦门市", "91路", "1")
    assert isinstance(client.public_query("116", {"CITYNAME": "厦门市", "DIRECTION": "1", "ROUTEID": route["routeId"], "CITYKEY": ""})["list"], list)
    assert client.public_query("205", {"CITYKEY": "qz595803"})["city"]["cityname"] == "泉州市"
    assert client.public_query("204", {"CITYNAME": "厦门市"})["status"] == 1
    assert isinstance(client.public_query("203", {"CITYNAME": "厦门市", "CITYKEY": ""})["data"], list)
    assert isinstance(client.public_notices("厦门市", [{"lineName": "91路", "direction": "1"}])["info"], list)
    assert client.public_query("105", {"CITYNAME": "厦门市", "STATIONNAME": "高崎T4公交场站", "MYLAT": "", "MYLNG": "", "CITYKEY": ""})["data"]
    params = {"CITYNAME": "厦门市", "CITYKEY": "", "STARTPOINTNAME": route["data"][2]["stationName"], "STARTPOINTLNG": route["data"][2]["station_lon"], "STARTPOINTLAT": route["data"][2]["station_lat"], "ENDPOINTNAME": route["data"][-3]["stationName"], "ENDPOINTLNG": route["data"][-3]["station_lon"], "ENDPOINTLAT": route["data"][-3]["station_lat"]}
    assert client.public_query("111", params)["info"]


def test_featured_routes(client):
    result = client.featured_routes("0772")
    assert result["code"] == 10000 and result["data"]
    assert all(line["routeName"] and line["direction"] for line in result["data"])


@pytest.mark.parametrize("command,params", [
    ("999", {}), ("103", {"CITYNAME": "广州市"}),
    ("103", {"CITYNAME": "", "LINENAME": "1路", "DIRECTION": "1"}),
    ("103", {"CITYNAME": "广州市", "LINENAME": "1路", "DIRECTION": "3"}),
    ("101", {"CMD": "103"}),
    ("104", {"CITYNAME": "广州市", "LINENAME": "1路", "DIRECTION": "1", "STATIONORDER": 0}),
    ("104", {"CITYNAME": "广州市", "LINENAME": "1路", "DIRECTION": "1", "STATIONORDER": 1.5}),
    ("207", {"CITYNAME": "广州市", "ROUTEID": True, "DIRECTION": "1"}),
])
def test_public_parameter_validation(client, command, params):
    with pytest.raises(ValueError):
        client.public_query(command, params)
