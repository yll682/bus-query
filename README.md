# 候车 · 公交查询

打开首页查询附近公交站，查看线路、乘车站、实时到站提示和发车时刻表。页面适配手机和电脑，支持城市选择、同名站台切换、收藏和最近搜索。

## 菜单式部署

支持 Debian 12 及以上版本、Ubuntu 22.04 及以上版本，需要 root 权限、systemd 和服务器能够访问 GitHub、PyPI 及公交数据服务。

国际线路：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/yll682/bus-query/main/deploy.sh)
```

国内线路（EdgeOne 加速）：

```bash
bash <(curl -fsSL https://edgeone.gh-proxy.org/https://raw.githubusercontent.com/yll682/bus-query/main/deploy.sh)
```

菜单提供：

1. 安装 / 更新：首次填写监听端口，默认 `8765`。自动安装 Python 依赖、下载 GitHub Release 中已经构建好的网页、校验文件、创建独立系统用户并启动服务。
2. 重启服务：重启并检查服务是否能够访问。
3. 查看状态：显示服务状态和本机查询地址。
4. 卸载：输入 `yes` 后删除本项目的 systemd 服务、系统用户、安装目录和配置。
5. 退出。

更新时保留监听端口和设备标识。新版本完成文件检查与依赖安装后替换当前版本并重启。安装目录为 `/opt/bus-query`；浏览器中的收藏保存在用户设备上。

服务器运行期间无需 Node.js。GitHub Actions 负责构建网页、验证发布文件并在真实 systemd 环境测试安装、更新、重启与卸载，通过后生成新 Release。

## 域名与 HTTPS

服务仅监听 `127.0.0.1:<端口>`。在服务器已有的 Nginx 或 Caddy 中，将网站域名转发到这个地址，并启用 HTTPS。公网自动定位需要 HTTPS 和用户的位置授权。

`deploy/nginx.conf` 提供 Nginx 配置示例，包含查询频率和并发限制。使用时填写实际域名及安装时选择的端口，再为这个域名配置 HTTPS。安装和卸载程序保留服务器上已有的反向代理及其他网站配置。

查询参数包含位置，反向代理应关闭访问日志，并避免在错误日志中记录请求参数。示例关闭访问日志，错误日志仅记录严重系统错误。应用日志仅记录接口路径、状态、耗时和查询编号。

## 常用管理命令

```bash
systemctl status bus-query
systemctl restart bus-query
journalctl -u bus-query -f
curl -fsS http://127.0.0.1:8765/health
```

服务配置保存在 `/opt/bus-query/config.json`，包含 `port` 和 `deviceId`。需要修改时编辑这个文件，再通过部署菜单选择“安装 / 更新”，程序验证配置并生成服务环境文件。

安装程序使用项目标识检查安装目录、服务文件和系统用户，删除范围固定为本项目。系统依赖包与浏览器收藏继续保留。

## 本地运行

```powershell
python -m pip install -r requirements.txt
Set-Location web
npm ci
npm run build
Set-Location ..
.\start.ps1
```

浏览器访问 `http://127.0.0.1:8765/`。

```powershell
python -X utf8 -m pytest tests -q
python -X utf8 bus_api_client.py --verify
```

网站接口与浏览器测试直接查询真实公交服务。安装程序生命周期测试位于 `deploy/test_lifecycle.py`，在 GitHub Actions 的 Ubuntu systemd 环境执行。

## 数据范围与隐私

- 厦门查询使用厦门公交接口，其他城市使用掌上公交公开 H5 查询服务。配置共包含 575 条城市查询记录。
- 城市列表、线路搜索和站点资料的存在，均不能保证该线路提供实时车辆。页面依据上游返回状态提示实时查询是否可用。
- 自动定位会向公交数据服务发送查询位置；浏览器使用 BigDataCloud 识别城市，站点地图使用 OpenStreetMap。
- 网站无需登录，收藏仅保存在当前浏览器。服务端查询缓存存在内存中，15 秒过期。
- 公网使用需要确认上游服务的授权使用范围，遵守查询频率限制。服务可用性依赖上游，接口可能调整。

页面操作和验证范围见 `网站使用说明.md`。接口参数、签名与数据字段见 `公交查询接口文档.md` 和 `掌上公交_7.5.0_查询接口分析.md`。
