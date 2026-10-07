import json
import logging
import time
from uuid import uuid4
from typing import Annotated, Literal

import requests
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from website import service
from bus_api_client import UpstreamError


app = FastAPI(title="候车 · 公交查询", version="1.0.0")
LOG = logging.getLogger("bus-web")
LOG.setLevel(logging.INFO)
LOG.addHandler(logging.StreamHandler())
DIST = service.ROOT / "web" / "dist"
if not (DIST / "index.html").is_file():
    raise FileNotFoundError("页面尚未构建，请在 web 目录执行 npm run build")
CityKey = Annotated[str, Query(min_length=1, max_length=8)]
Name = Annotated[str, Query(min_length=1, max_length=100)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Direction = Literal["1", "2"]


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid4().hex
    started = time.monotonic()
    response = await call_next(request)
    response.headers.update({"X-Request-ID": request.state.request_id,
                             "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "strict-origin-when-cross-origin",
                             "Permissions-Policy": "geolocation=(self)",
                             "X-Frame-Options": "DENY"})
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path in {"/sw.js", "/manifest.webmanifest"}:
        response.headers["Cache-Control"] = "no-cache"
    LOG.info(json.dumps({"requestId": request.state.request_id, "path": request.url.path,
                         "status": response.status_code, "durationMs": round((time.monotonic() - started) * 1000)}))
    return response


@app.exception_handler(service.QueryError)
async def query_error(request, exc):
    return JSONResponse({"message": str(exc), "requestId": request.state.request_id}, status_code=exc.status)


@app.exception_handler(requests.RequestException)
async def network_error(request, exc):
    LOG.error(json.dumps({"requestId": request.state.request_id, "errorType": type(exc).__name__}))
    return JSONResponse({"message": "公交数据服务连接失败，请稍后重新查询。", "requestId": request.state.request_id}, status_code=502)


@app.exception_handler(ValueError)
async def upstream_error(request, exc):
    LOG.error(json.dumps({"requestId": request.state.request_id, "errorType": type(exc).__name__}))
    return JSONResponse({"message": "上游查询未成功或返回了无法识别的数据。", "requestId": request.state.request_id}, status_code=502)


@app.exception_handler(UpstreamError)
async def rejected_query(request, exc):
    LOG.warning(json.dumps({"requestId": request.state.request_id, "endpoint": exc.path, "upstreamStatus": exc.code}))
    message = "上游没有提供这条线路的站点列表。" if exc.path == "getStation" else "上游未接受本次公交查询。"
    return JSONResponse({"message": message, "requestId": request.state.request_id}, status_code=502)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    fields = ", ".join(str(error["loc"][-1]) for error in exc.errors())
    return JSONResponse({"message": f"请检查查询参数：{fields}", "requestId": request.state.request_id}, status_code=422)


@app.get("/health")
@app.get("/ready")
def health():
    return {"status": "ok", "cities": len(service.CITIES)}


@app.get("/api/cities")
def cities():
    return service.CITIES


@app.get("/api/nearby")
def nearby(city: CityKey, lat: Latitude, lng: Longitude):
    return service.nearby(service.city_for(city), lat, lng)


@app.get("/api/search")
def search(city: CityKey, keyword: Name, kind: Literal["line", "station", "all"] = "line"):
    return service.search(service.city_for(city), keyword, kind)


@app.get("/api/station")
def station(city: CityKey, name: Name, number: str = "",
            lat: Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)] = None,
            lng: Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)] = None):
    if (lat is None) != (lng is None):
        raise service.QueryError("经度和纬度需要同时提供", 422)
    return service.station_detail(service.city_for(city), name, number, lat, lng)


@app.get("/api/station-buses")
def station_buses(city: CityKey, name: Name, lat: Latitude, lng: Longitude,
                  number: Annotated[str, Query(max_length=80)] = ""):
    return service.station_buses(service.city_for(city), name, number, lat, lng)


@app.get("/api/line")
def line(city: CityKey, name: Name, direction: Direction):
    return service.line_detail(service.city_for(city), name, direction)


@app.get("/api/vehicles")
def vehicles(city: CityKey, name: Name, direction: Direction, lat: Latitude, lng: Longitude,
             line_id: str = "", station_id: str = "", station_name: str = "",
             station_order: Annotated[int | None, Query(ge=1)] = None):
    return service.vehicles(service.city_for(city), name, direction, line_id, station_id,
                            station_name, station_order, lat, lng)


@app.get("/api/arrival")
def arrival(city: CityKey, name: Name, direction: Direction, station_name: Name,
            station_order: Annotated[int, Query(ge=1)]):
    return service.arrival(service.city_for(city), name, direction, station_name, station_order)


@app.get("/api/timetable")
def timetable(city: CityKey, name: Name, line_id: Name, direction: Direction):
    return service.timetable(service.city_for(city), name, line_id, direction)


app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=DIST), name="public")
