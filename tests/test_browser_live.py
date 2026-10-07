import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import sync_playwright, expect


BASE = os.environ.get("BUS_TEST_URL", "http://127.0.0.1:8765")
RESULTS = Path(__file__).resolve().parent.parent / "work" / "browser-tests"


@pytest.fixture(scope="module")
def browser():
    RESULTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


def manual_position(page, lat, lng):
    page.get_by_role("button", name="选择位置", exact=True).click()
    coordinates = page.get_by_role("dialog").locator("details")
    if not coordinates.evaluate("element => element.open"):
        coordinates.locator("summary").click()
    page.get_by_label("纬度", exact=True).fill(str(lat))
    page.get_by_label("经度", exact=True).fill(str(lng))
    with page.expect_response(lambda response: "/api/nearby?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="查询这个位置附近的站点").click()
    assert response.value.status == 200, response.value.text()
    expect(page.locator(".station-card").first).to_be_visible(timeout=60000)
    return response.value.json()["data"]["stations"]


def search_line(page, name):
    page.get_by_role("button", name="搜索线路、公交站名").click()
    page.get_by_label("线路或站点名称").fill(name)
    with page.expect_response(lambda response: "/api/search?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="搜索", exact=True).click()
    assert response.value.status == 200, response.value.text()
    expect(page.locator(".result-row").first).to_be_visible(timeout=60000)
    return response.value.json()["data"]


@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844), (320, 720)])
def test_xiamen_browser(browser, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    stations = manual_position(page, 24.54193506, 118.15230555)
    expect(page.locator(".station-card.nearest h3")).to_have_text(stations[0]["name"])
    expect(page.locator(".station-card")).to_have_count(len(stations))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name=f"查询站点 {stations[0]['name']}", exact=True).click()
    expect(page.locator(".detail-heading h1")).to_have_text(stations[0]["name"])
    page.get_by_role("button", name="收藏站点", exact=True).click()
    expect(page.get_by_role("button", name="取消收藏站点", exact=True)).to_be_visible()
    page.locator(".brand").click()
    searches = search_line(page, "91路")
    with page.expect_response(lambda response: "/api/line?" in response.url, timeout=60000) as response:
        page.locator(".result-row").filter(has=page.locator(".route-number", has_text=re.compile(r"^91路$"))).first.click()
    assert response.value.status == 200, response.value.text()
    route = response.value.json()["data"]
    expect(page.locator(".route-heading h1")).to_have_text("91路", timeout=60000)
    expect(page.locator(".stop-list li")).to_have_count(len(route["stations"]))
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    expect(page.locator(".route-live .error")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="收藏线路", exact=True).click()
    expect(page.get_by_role("button", name="取消收藏线路", exact=True)).to_be_visible()
    page.locator(".diagram-stop").nth(2).click()
    page.locator(".diagram-stop").nth(4).click()
    expect(page.locator(".boarding-heading h2")).to_have_text(route["stations"][4]["name"])
    expect(page.locator(".diagram-stop[aria-pressed='true']")).to_have_count(1)
    expect(page.locator(".stop-list .current")).to_have_count(1)
    with page.expect_response(lambda response: "/api/line?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="切换方向").click()
    assert response.value.status == 200
    reverse = response.value.json()["data"]
    assert reverse["direction"] != route["direction"]
    expect(page.locator(".route-destination h2")).to_have_text(reverse["to"])
    page.get_by_role("button", name="发车时刻表").click()
    expect(page.get_by_role("dialog")).to_be_visible(timeout=60000)
    assert page.locator(".time-grid span").count() > 0
    page.get_by_role("button", name="关闭时刻表").click()
    page.get_by_role("button", name="收藏", exact=True).click()
    expect(page.locator(".result-row")).to_have_count(2)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "页面出现横向滚动"
    page.reload(wait_until="networkidle")
    page.get_by_role("button", name="收藏", exact=True).click()
    expect(page.locator(".result-row")).to_have_count(2)
    assert not failures, failures
    (RESULTS / f"xiamen-{width}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    context.close()


def test_guangzhou_browser(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".city-button")).to_contain_text("厦门市", timeout=15000)
    page.locator(".city-button").click()
    page.get_by_label("城市名称或拼音").fill("guangzhou")
    page.locator(".city-list button").filter(has_text="广州市").click()
    stations = manual_position(page, 23.1291, 113.2644)
    expect(page.locator(".station-card")).to_have_count(len(stations))
    searches = search_line(page, "1路")
    with page.expect_response(lambda response: "/api/line?" in response.url, timeout=60000) as response:
        page.locator(".result-row").first.click()
    assert response.value.status == 200, response.value.text()
    route = response.value.json()["data"]
    expect(page.locator(".route-heading h1")).to_have_text(searches[0]["name"])
    expect(page.locator(".stop-list li")).to_have_count(len(route["stations"]))
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    expect(page.locator(".route-live .error")).to_have_count(0)
    expect(page.locator(".stop-list button")).to_have_count(len(route["stations"]))
    page.get_by_role("button", name="选择乘车站", exact=True).click()
    stop = route["stations"][5]
    page.get_by_label("筛选沿途站点").fill(stop["name"])
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as live:
        page.locator(".stop-options button").filter(has_text=stop["name"]).first.click()
    assert live.value.status == 200, live.value.text()
    for arrival in live.value.json()["data"]["arrivals"]:
        if arrival["statusText"]:
            expect(page.locator(".arrival-strip")).to_contain_text(arrival["statusText"])
        if arrival["timeText"]:
            expect(page.locator(".arrival-strip")).to_contain_text(arrival["timeText"])
    with page.expect_response(lambda response: "/api/timetable?" in response.url, timeout=60000) as table_response:
        page.get_by_role("button", name="发车时刻表", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible(timeout=60000)
    assert table_response.value.status == 200, table_response.value.text()
    times = table_response.value.json()["data"]["times"]
    expect(page.locator(".time-grid span")).to_have_count(len(times))
    table = table_response.value.json()["data"]
    for group in table["groups"]:
        valid_times = [item for item in group["times"] if item["isDelete"] != 1]
        if valid_times:
            period = page.locator(".timetable-period").filter(has=page.locator("summary", has_text=group["group"]))
            expect(period.locator(".time-grid span")).to_have_count(len(valid_times))
            expect(period.locator(".past-time")).to_have_count(sum(item["status"] == 1 for item in valid_times))
            expect(period.locator(".current-time")).to_have_count(sum(item["status"] == 2 for item in valid_times))
    if table["nextDeparture"]:
        expect(page.get_by_role("dialog").locator(".departure-note")).to_contain_text(table["nextDeparture"])
    if not times:
        expect(page.get_by_role("dialog")).to_contain_text("当前方向没有发车时刻资料")
    page.keyboard.press("Escape")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not failures, failures
    (RESULTS / "guangzhou-390.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    context.close()


def test_shenzhen_route_sections(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.locator(".city-button").click()
    page.get_by_label("城市名称或拼音").fill("shenzhen")
    page.locator(".city-list button").filter(has_text="深圳市").click()
    manual_position(page, 22.5431, 114.0579)
    search_line(page, "M200路")
    page.locator(".result-row").first.click()
    expect(page.locator(".route-heading h1")).to_have_text("M200路", timeout=60000)
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    assert page.locator(".diagram-stop").count() > 0
    expect(page.locator(".route-stops .error")).to_have_count(0)
    expect(page.locator(".route-live .error")).to_have_count(0)
    page.get_by_role("button", name="收藏线路", exact=True).click()
    expect(page.get_by_role("button", name="取消收藏线路", exact=True)).to_be_visible()
    context.close()


def test_real_refresh_and_station_map(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    manual_position(page, 24.54193506, 118.15230555)
    page.get_by_role("button", name="选择位置", exact=True).click()
    page.get_by_role("button", name="打开地图选择位置").click()
    expect(page.locator(".leaflet-container")).to_be_visible(timeout=15000)
    expect(page.locator(".leaflet-tile-loaded").first).to_be_visible(timeout=30000)
    assert page.locator(".leaflet-overlay-pane path").count() >= 2
    page.get_by_role("button", name="关闭位置选择").click()
    search_line(page, "91路")
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as response:
        page.locator(".result-row").filter(has=page.locator(".route-number", has_text=re.compile(r"^91路$"))).first.click()
    first_time = response.value.json()["fetchedAt"]
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=40000) as response:
        expect(page.locator(".route-heading h1")).to_have_text("91路")
    assert response.value.status == 200
    assert response.value.json()["fetchedAt"] != first_time
    assert not failures, failures
    context.close()


@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844), (320, 720)])
def test_station_name_position_and_platforms(browser, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    expect(page.locator(".search-guidance")).to_contain_text("无需定位也可以搜索线路")
    page.get_by_role("button", name="切换城市", exact=True).click()
    expect(page.get_by_label("城市名称或拼音")).to_be_focused()
    for _ in range(4):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement === document.body || document.activeElement.closest('dialog[open]') !== null")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("button", name="切换城市", exact=True)).to_be_focused()

    page.get_by_role("button", name="选择位置", exact=True).click()
    expect(page.get_by_label("附近的公交站名")).to_be_focused()
    assert not page.get_by_role("dialog").locator("details").evaluate("element => element.open")
    page.get_by_label("附近的公交站名").fill("北附学校思齐中学")
    with page.expect_response(lambda response: "/api/search?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="查找公交站", exact=True).click()
    assert response.value.status == 200, response.value.text()
    names = [item["name"] for item in response.value.json()["data"]]
    assert "北附学校思齐中学站" in names
    with page.expect_response(lambda response: "/api/nearby?" in response.url, timeout=60000) as response:
        page.locator(".position-results").get_by_role("button", name="北附学校思齐中学站", exact=True).click()
    assert response.value.status == 200, response.value.text()
    stations = response.value.json()["data"]["stations"]
    station = stations[0]
    expect(page.get_by_role("dialog")).to_have_count(0, timeout=60000)
    expect(page.locator(".station-card.nearest h3")).to_have_text(station["name"])
    expect(page.locator(".nearest-label")).to_have_text("所选位置最近站点")
    assert len(station["platformNumbers"]) == 2
    page.get_by_role("button", name=f"查询站点 {station['name']}", exact=True).click()
    expect(page.locator(".detail-heading")).to_contain_text(station["number"], timeout=60000)
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    with page.expect_response(lambda response: "/api/station?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="反向站台", exact=True).click()
    assert response.value.status == 200, response.value.text()
    reverse = response.value.json()["data"]
    assert reverse["number"] != station["number"]
    expect(page.locator(".detail-heading")).to_contain_text(reverse["number"])
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    page.get_by_label("筛选线路或开往方向").fill("803")
    expect(page.locator(".result-row")).to_have_count(len(reverse["lines"]))
    with page.expect_response(lambda response: "/api/line?" in response.url, timeout=60000) as response:
        page.locator(".result-row").first.click()
    assert response.value.status == 200, response.value.text()
    line = response.value.json()["data"]
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    button = page.get_by_role("button", name="选择乘车站", exact=True)
    button.scroll_into_view_if_needed()
    assert button.bounding_box()["height"] >= 44
    button.click()
    stop = line["stations"][2]
    page.get_by_label("筛选沿途站点").fill(stop["name"])
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as response:
        page.locator(".stop-options button").filter(has_text=stop["name"]).first.click()
    assert response.value.status == 200, response.value.text()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.locator(".boarding-heading h2")).to_have_text(stop["name"])
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="返回站点详情", exact=True).click()
    expect(page.locator(".detail-heading")).to_contain_text(reverse["number"])
    page.locator(".page-bar").get_by_role("button", name="返回附近站点", exact=True).click()
    expect(page.locator(".station-card.nearest h3")).to_have_text(station["name"])
    assert not failures, failures
    (RESULTS / f"station-name-position-{width}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    context.close()


def test_search_return_and_tabs(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    searches = search_line(page, "91路")
    page.locator(".result-row").first.click()
    expect(page.locator(".route-heading h1")).to_have_text(searches[0]["name"], timeout=60000)
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    page.get_by_role("button", name="切换方向").click()
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    page.get_by_role("button", name="返回搜索结果", exact=True).click()
    expect(page.get_by_label("线路或站点名称")).to_have_value("91路")
    expect(page.locator(".result-row")).to_have_count(len(searches))
    with page.expect_response(lambda response: "/api/search?" in response.url, timeout=60000) as response:
        page.get_by_role("group", name="搜索类型").get_by_role("button", name="站点", exact=True).click()
    assert response.value.status == 200, response.value.text()
    assert "kind=station" in response.value.url
    expect(page.get_by_role("group", name="搜索类型").get_by_role("button", name="站点", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_label("线路或站点名称")).to_have_value("91路")
    context.close()


def test_national_station_search_and_platforms(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    page.get_by_role("button", name="切换城市", exact=True).click()
    page.get_by_label("城市名称或拼音").fill("guangzhou")
    page.locator(".city-list button").filter(has_text="广州市").click()
    page.get_by_role("button", name="搜索线路、公交站名").click()
    page.get_by_role("group", name="搜索类型").get_by_role("button", name="站点", exact=True).click()
    page.get_by_label("线路或站点名称").fill("公园前")
    with page.expect_response(lambda response: "/api/search?" in response.url, timeout=60000) as response:
        page.get_by_role("button", name="搜索", exact=True).click()
    assert response.value.status == 200, response.value.text()
    results = response.value.json()["data"]
    assert results
    expect(page.locator(".result-list button")).to_have_count(len(results))
    with page.expect_response(lambda response: "/api/station?" in response.url, timeout=60000) as station_response:
        page.locator(".result-row").first.click()
    assert station_response.value.status == 200, station_response.value.text()
    station = station_response.value.json()["data"]
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    expect(page.locator(".station-line")).to_have_count(len(station["lines"]))
    assert station["lines"] and station["platforms"]
    if len(station["platforms"]) > 1:
        page.get_by_role("button", name="切换站台", exact=True).click()
        with page.expect_response(lambda response: "/api/station?" in response.url, timeout=60000) as reverse_response:
            page.get_by_role("dialog").locator(".position-results button").first.click()
        assert reverse_response.value.status == 200, reverse_response.value.text()
        reverse = reverse_response.value.json()["data"]
        assert (reverse["lat"], reverse["lng"]) != (station["lat"], station["lng"])
        expect(page.locator(".loading")).to_have_count(0, timeout=60000)
        expect(page.locator(".station-line")).to_have_count(len(reverse["lines"]))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not failures, failures
    context.close()


def visible_count(page, selector):
    return page.locator(selector).evaluate_all("""elements => elements.filter(element => {
        const box = element.getBoundingClientRect();
        const limit = document.querySelector('.bottom-nav').getBoundingClientRect().top;
        const clip = element.closest('.route-diagram')?.getBoundingClientRect();
        return element.checkVisibility() && box.width > 0 && box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= limit && (!clip || (box.left >= clip.left && box.right <= clip.right));
    }).length""")


@pytest.mark.parametrize("width,height,minimum", [(320, 568, 5), (360, 640, 6), (390, 844, 10)])
def test_small_screen_density_and_route_panels(browser, width, height, minimum):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    stations = manual_position(page, 24.54193506, 118.15230555)
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    assert visible_count(page, ".station-card") >= 1
    card = page.locator(".station-card").first
    expect(card.locator(".line-chips button")).to_have_count(min(3, len(stations[0]["lines"])))
    assert visible_count(page, ".station-card.nearest .line-chips button") >= 3
    if len(stations[0]["lines"]) > 3:
        card.get_by_role("button", name=f"全部 {len(stations[0]['lines'])} 条线路").click()
        expect(card.locator(".line-chips button")).to_have_count(len(stations[0]["lines"]))
        card.get_by_role("button", name="收起线路", exact=True).click()
        expect(card.locator(".line-chips button")).to_have_count(3)
    page.locator(".brand").click()
    searches = search_line(page, "91")
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    assert len(searches) >= minimum
    assert visible_count(page, ".result-row") >= minimum
    with page.expect_response(lambda response: "/api/line?" in response.url, timeout=60000) as response:
        page.locator(".result-row").first.click()
    assert response.value.status == 200
    route = response.value.json()["data"]
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    expect(page.locator(".diagram-stop")).to_have_count(len(route["stations"]))
    assert visible_count(page, ".diagram-stop") >= 5
    assert visible_count(page, ".choose-stop") == 1
    assert not page.locator(".all-stops").evaluate("element => element.open")
    buttons = page.locator(".choose-stop, .switch-direction, .route-heading .save-button, .route-panel-bar button, .diagram-stop")
    assert buttons.evaluate_all("elements => elements.every(element => element.getBoundingClientRect().height >= 44)")
    page.get_by_role("button", name="选择乘车站", exact=True).click()
    last = route["stations"][-1]
    page.get_by_label("筛选沿途站点").fill(last["name"])
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as response:
        page.locator(".stop-options button").filter(has_text=last["name"]).last.click()
    assert response.value.status == 200
    vehicles = response.value.json()["data"]["vehicles"]
    expect(page.locator(".boarding-heading h2")).to_have_text(last["name"])
    expect(page.locator(".diagram-stop[aria-pressed='true']")).to_have_attribute("aria-label", f"{last['order']}. {last['name']}，选择乘车站")
    assert page.locator(".route-diagram").evaluate("element => element.scrollLeft > 0")
    assert visible_count(page, ".diagram-stop[aria-pressed='true']") == 1
    page.get_by_role("group", name="线路显示内容").get_by_role("button", name=re.compile("车辆列表")).click()
    expect(page.locator(".vehicle-row")).to_have_count(len(vehicles))
    expect(page.locator(".route-diagram")).to_have_count(0)
    page.get_by_role("group", name="线路显示内容").get_by_role("button", name="站点图", exact=True).click()
    expect(page.locator(".diagram-stop")).to_have_count(len(route["stations"]))
    page.locator(".all-stops > summary").click()
    expect(page.locator(".stop-list button").first).to_be_visible()
    page.get_by_role("button", name="发车时刻表", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible(timeout=60000)
    period = page.locator(".timetable-period").first
    assert page.locator(".time-grid span").count() > 0
    period.locator("summary").click()
    assert not period.evaluate("element => element.open")
    period.locator("summary").click()
    expect(period.locator(".time-grid span").first).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not failures, failures
    context.close()


def test_nearby_live_preview_and_station_rows(browser):
    context = browser.new_context(viewport={"width": 360, "height": 640})
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle")
    expect(page.locator(".location-panel strong")).to_contain_text("自动定位未完成", timeout=30000)
    with page.expect_response(lambda response: "/api/station-buses?" in response.url, timeout=60000) as response:
        stations = manual_position(page, 24.54193506, 118.15230555)
    assert response.value.status == 200
    first_time = response.value.json()["fetchedAt"]
    preview_url = response.value.url
    with page.expect_response(lambda item: item.url == preview_url, timeout=40000) as next_response:
        expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    assert next_response.value.status == 200
    assert next_response.value.json()["fetchedAt"] != first_time
    station = stations[0]
    with page.expect_response(lambda item: "/api/station-buses?" in item.url and parse_qs(urlparse(item.url).query).get("number") == [station["number"]], timeout=60000) as buses_response:
        page.get_by_role("button", name=f"查询站点 {station['name']}", exact=True).click()
    assert buses_response.value.status == 200
    buses = buses_response.value.json()["data"]
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    expect(page.locator(".result-row")).to_have_count(len(station["lines"]))
    expect(page.locator(".arrival-row")).to_have_count(0)
    for bus in buses:
        lines = [line for line in station["lines"] if line["name"] == bus["name"] and line["direction"] == bus["direction"]]
        if lines and bus["remainingStations"] is not None and not bus["nextDeparture"]:
            row = page.locator(".result-row").filter(has=page.locator(".route-number", has_text=re.compile(f"^{re.escape(bus['name'])}$"))).filter(has_text=bus["to"])
            expect(row.first).to_contain_text(f"{bus['remainingStations']} 站")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.close()
