import os
import re

import pytest
from playwright.sync_api import expect, sync_playwright


BASE = os.environ.get("BUS_TEST_URL", "http://127.0.0.1:8765")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


def ready(page):
    page.evaluate("async () => { await navigator.serviceWorker.ready }")
    if not page.evaluate("navigator.serviceWorker.controller !== null"):
        page.reload(wait_until="networkidle")
    page.wait_for_function("navigator.serviceWorker.controller !== null")


def cache_urls(page):
    return page.evaluate("async () => (await Promise.all((await caches.keys()).map(async name => (await (await caches.open(name)).keys()).map(request => request.url)))).flat()")


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_pwa_manifest_installability_and_offline_shell(browser, width):
    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE, wait_until="networkidle")
    ready(page)
    cdp = context.new_cdp_session(page)
    manifest = cdp.send("Page.getAppManifest")
    assert not manifest["errors"]
    assert cdp.send("Page.getInstallabilityErrors")["installabilityErrors"] == []
    icons = page.evaluate("""async () => {
        const manifest = await (await fetch('/manifest.webmanifest')).json();
        return Promise.all(manifest.icons.map(async icon => {
            const image = new Image(); image.src = icon.src; await image.decode();
            return {expected: icon.sizes, actual: `${image.naturalWidth}x${image.naturalHeight}`};
        }));
    }""")
    assert all(icon["actual"] == icon["expected"] for icon in icons)
    assert not any("/api/" in url for url in cache_urls(page))
    page.get_by_role("button", name="安装到桌面", exact=True).click()
    expect(page.get_by_role("dialog")).to_contain_text("Safari")
    page.keyboard.press("Escape")
    context.set_offline(True)
    page.reload(wait_until="networkidle")
    expect(page.locator(".offline-banner")).to_contain_text("实时查询已暂停")
    assert page.evaluate("navigator.onLine") is False
    assert page.evaluate("async () => { try { await fetch('/api/cities'); return false } catch { return true } }")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.set_offline(False)
    expect(page.locator(".offline-banner")).to_have_count(0)
    expect(page.locator(".city-button")).to_contain_text("厦门市", timeout=30000)
    assert not errors, errors
    context.close()


def test_offline_clears_live_vehicles_and_restores_route(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle")
    ready(page)
    page.get_by_role("button", name="搜索线路、公交站名").click()
    page.get_by_label("线路或站点名称").fill("91路")
    page.get_by_role("button", name="搜索", exact=True).click()
    page.locator(".search-lines .result-row").first.click(timeout=60000)
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as live:
        page.locator(".diagram-stop").nth(19).click()
    assert live.value.status == 200
    vehicles = live.value.json()["data"]["vehicles"]
    stop_name = page.locator(".boarding-heading h2").inner_text()
    page.get_by_role("group", name="线路显示内容").get_by_role("button", name=re.compile("车辆列表")).click()
    expect(page.locator(".vehicle-row")).to_have_count(len(vehicles))
    assert page.locator(".vehicle-row strong").all_text_contents() == [vehicle["plate"] for vehicle in vehicles]
    route_url = page.url
    context.set_offline(True)
    expect(page.locator(".offline-banner")).to_be_visible()
    expect(page.locator(".vehicle-row, .arrival-highlight")).to_have_count(0)
    expect(page.locator(".route-live .error")).to_contain_text("当前离线")
    page.reload(wait_until="networkidle")
    assert page.url == route_url
    expect(page.locator(".offline-banner")).to_be_visible()
    with page.expect_response(lambda response: "/api/vehicles?" in response.url, timeout=60000) as restored:
        context.set_offline(False)
    assert restored.value.status == 200
    expect(page.locator(".boarding-heading h2")).to_have_text(stop_name)
    expect(page.get_by_role("group", name="线路显示内容").get_by_role("button", name=re.compile("车辆列表"))).to_have_attribute("aria-pressed", "true")
    assert page.url == route_url
    assert not any("/api/" in url for url in cache_urls(page))
    context.close()


def test_station_waiting_distance_display(browser):
    context = browser.new_context(viewport={"width": 320, "height": 720})
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.get_by_role("button", name="搜索线路、公交站名").click()
    page.get_by_label("线路或站点名称").fill("高崎T4公交场站")
    page.get_by_role("button", name="搜索", exact=True).click()
    with page.expect_response(lambda response: "/api/station-buses?" in response.url, timeout=60000) as live:
        page.locator(".search-stations .result-row").first.click(timeout=60000)
    assert live.value.status == 200
    expect(page.locator(".loading")).to_have_count(0, timeout=60000)
    for bus in live.value.json()["data"]:
        if bus["waiting"]:
            row = page.locator(".station-line").filter(has=page.locator(".route-number", has_text=re.compile("^" + re.escape(bus["name"]) + "$"))).filter(has_text=f"开往 {bus['to']}").first
            expect(row).not_to_contain_text("0 米")
            expect(row).not_to_contain_text("剩余 0 站")
            expect(row).to_contain_text("计划发车" if bus["nextDeparture"] else "等待发车")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.close()
