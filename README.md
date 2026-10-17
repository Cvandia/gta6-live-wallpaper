<div align="center">

# GTA VI · 北京时间倒计时壁纸

[![Build](https://github.com/Cvandia/gta6-live-wallpaper/actions/workflows/build.yml/badge.svg)](https://github.com/Cvandia/gta6-live-wallpaper/actions/workflows/build.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-项目管理-DE5FE9)](https://docs.astral.sh/uv/)
[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4)](https://github.com/Cvandia/gta6-live-wallpaper)
[![License](https://img.shields.io/github/license/Cvandia/gta6-live-wallpaper)](LICENSE.txt)
[![Last Commit](https://img.shields.io/github/last-commit/Cvandia/gta6-live-wallpaper)](https://github.com/Cvandia/gta6-live-wallpaper/commits/)
[![GitHub Stars](https://img.shields.io/github/stars/Cvandia/gta6-live-wallpaper?style=social)](https://github.com/Cvandia/gta6-live-wallpaper/stargazers)

霓虹轮廓 · 人物鼠标视差 · 北京时间倒计时

<img src="docs/preview.gif" alt="GTA VI 壁纸动态预览" width="960">

<details>
<summary>查看静态预览</summary>
<img src="docs/preview.png" alt="GTA VI 壁纸静态预览" width="960">
</details>

</div>

## 📖 项目简介

以 GTA VI 官方海报为参考的 Windows 动态桌面壁纸，采用日落紫粉色界面。提供 EXE 与 Wallpaper Engine 网页版，显示距离发售的天、时、分、秒，以及固定采用北京时间的实时钟表。

Python 项目由 **uv** 管理虚拟环境和依赖，EXE 用户无需安装 Python。

## ✨ 功能

- 💜 **VI 霓虹轮廓**：EXE 与 Web 共用原网页的 105° 渐变流动、柔和呼吸和 16 处轮廓星芒
- ⏱️ **时间光效**：倒计时数字和右上角北京时间同步发光，秒级更新
- 🖱️ **人物分层视差**：人物随鼠标左右平滑轻移，默认在 1920 像素宽度下最大为 **±12 px**
- 🧠 **内存优化**：限定位图缓存，按显示大小加载绘图资源，并在设置或缩放变化时释放旧缓存
- ✨ **64 个高亮粒子**：Web 与 EXE 共用固定种子、颜色、尺寸、上浮轨迹和短尾光，附柔光与粉色进度条
- ⚙️ 可设置目标时间、光强、视差强度、时钟、帧率与文字大小
- 🖥️ 支持独立桌面模式与 Wallpaper Engine 导入

两版从 `assets/effects-spec.json` 读取同一套动效参数，使用一致的相位逻辑；Qt 与浏览器的抗锯齿、模糊和混合实现仍可能带来细微观感差别。

## 🚀 下载与使用

[下载入口](https://github.com/Cvandia/gta6-live-wallpaper/releases/latest) · [查看构建状态](https://github.com/Cvandia/gta6-live-wallpaper/actions/workflows/build.yml)

Release 提供 EXE、完整 ZIP 与 Web ZIP。GitHub Actions 会在推送到 `main` 后测试并打包；已有同名标签时保留已有发布与附件。

### EXE 版

下载并解压完整 `GTA6-LiveWallpaper-v1.4.1.zip`，双击 `GTA6Wallpaper.exe` 即可预览。支持 Windows 10 / 11 x64。

在窗口内右键选择 **“独立设为桌面壁纸”**，可将壁纸放到主屏桌面图标后面。右键托盘的 **VI** 图标可打开设置、返回预览或退出。

预览时按 `F11` 切换全屏，按 `Esc` 返回；普通预览窗口中按 `Esc` 退出。

### 导入 Wallpaper Engine

| 版本 | 导入入口 | 使用方式 |
| --- | --- | --- |
| EXE | `GTA6Wallpaper.exe` | 在“创建壁纸”中按应用程序导入 |
| Web | `WallpaperEngine-Web/index.html` | 在“创建壁纸”中导入网页入口，保持整个文件夹完整 |

Web 版可单独下载 `GTA6-WallpaperEngine-Web-v1.4.1.zip`，在引擎右侧调节属性；EXE 版通过右键菜单或托盘打开设置。独立桌面模式与 Wallpaper Engine 模式选择一种运行即可。

## ⚙️ 设置

| 设置 | 默认值 / 说明 |
| --- | --- |
| 动态效果 | 开启微尘、柔光等效果 |
| 霓虹光效 | 开启 VI 与时间的渐变外发光 |
| 发光强度 | **85%** |
| 人物视差 | 开启，平滑跟随鼠标左右移动 |
| 视差强度 | 1920 像素宽度下最大 **±12 px**，按显示宽度缩放 |
| EXE 动画帧率 | **20 FPS**，可选 **10 / 20 / 30 FPS** |
| 北京时间 | 开启，固定为 `UTC+8` |
| Web 跟随系统减少动态偏好 | 默认关闭，可按需要开启 |

EXE 设置保存在 `%LOCALAPPDATA%/GTA6Wallpaper/settings.json`。关闭视差可让人物停止移动；图层资源不可用时回退到官方静态原画。

EXE 限制绘图位图缓存的数量与大小，按当前显示大小加载绘图资源；调整设置或改变缩放时释放旧缓存，减少长时间运行时的内存占用。

**内存实测：v1.2.0 在增强光效的同时降低了内存占用。**

以下为 v1.2.0 内存优化时的对照数据，并非 v1.4.1 的复测结果。

| 画面尺寸 | v1.1.1 私有提交内存 | v1.2.0 私有提交内存 | 降低约 |
| --- | ---: | ---: | ---: |
| 1920 × 1080 | 158.57 MiB | 57.10 MiB | 64% |
| 3840 × 2160 | 240.23 MiB | 123.04 MiB | 49% |

2026-10-16 在相同 Windows 环境中，对 Qt offscreen 源码进程的固定画面暖机后测量；实际占用随 DPI、窗口尺寸和系统变化，表中数值不代表内存上限。

程序离线运行，使用电脑系统时钟计算倒计时，不受系统选择的时区影响；不会后台校时或自动更改发售日期。

## 📅 发售时间说明

核查日期：**2026-10-15**。

Rockstar 公布的 GTA VI 发售日为 **2026 年 11 月 19 日**。港区 PlayStation Store 商品页列出的时间为 `2026-11-18 16:00 UTC`，换算后本项目默认目标为：

> **北京时间 2026 年 11 月 19 日 00:00:00（UTC+8）**

该时刻对应港区 PS5 数字版商店列示时间，其他地区及平台以各自商店为准。若官方调整日期，可在设置中修改目标时间。

倒计时到期后归零，不会显示负数。进度条从首支预告发布时刻起计算，并限制在 `0–100%`。

- [Rockstar 官方发售日期公告](https://www.rockstargames.com/newswire/article/ak3ak31a49a221/grand-theft-auto-vi-is-now-set-to-launch-november-19-2026)
- [港区 PlayStation Store 商品页](https://store.playstation.com/zh-hans-hk/product/EP1004-PPSA01547_00-GTAVISTANDARD001)

## 🛠️ 本地运行

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，随后在 Windows PowerShell 中执行：

```powershell
git clone https://github.com/Cvandia/gta6-live-wallpaper.git
cd gta6-live-wallpaper
uv sync --locked
uv run python src/main.py --preview
```

uv 会自动创建并使用 `.venv`，Python 版本由 `.python-version` 指定，依赖由 `uv.lock` 锁定。VS Code 中请选择 `.venv/Scripts/python.exe` 作为解释器。

独立桌面模式：

```powershell
uv run python src/main.py --desktop
```

本地预览网页版本，先从根目录素材生成 `web/assets/`，再启动静态服务器：

```powershell
uv run python tools/prepare_web.py
uv run python -m http.server 8000 --directory web
```

随后在浏览器访问 `http://localhost:8000`。准备工具同时从共享参数生成 `web/effects-data.js`，供网页离线读取；`web/assets/` 不重复提交到仓库，发行包中的 `WallpaperEngine-Web/` 已带齐素材，可直接导入。

## 📦 构建 EXE

在 Windows 项目根目录执行：

```powershell
uv sync --locked --group build
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

输出文件：

- `dist/GTA6Wallpaper.exe`：内置素材、Python 与 Qt 运行库的单文件程序
- `dist/GTA6-LiveWallpaper-v1.4.1.zip`：EXE、完整 Web 壁纸、说明与第三方许可
- `dist/GTA6-WallpaperEngine-Web-v1.4.1.zip`：完整网页壁纸与素材

GitHub Actions 在推送到 `main` 或手动运行后执行锁定依赖安装、Python / Web 测试及打包，并保存构建产物；首次成功构建会创建 `v1.4.1` Release。

## 📂 项目结构

```text
gta6-live-wallpaper/
├─ src/                  # Python / PySide6 壁纸程序
├─ assets/               # 原画、图层、字体、共享 effects-spec.json 与来源记录
├─ web/                  # Wallpaper Engine 网页版源码
├─ tests/                # 倒计时、动效、网页与窗口嵌入验证
├─ tools/                # 网页素材准备工具
├─ docs/                 # 预览与使用说明
├─ Licenses/             # 第三方许可文本
├─ .github/workflows/    # Windows 测试、打包与发布
├─ pyproject.toml        # 项目信息及依赖
├─ uv.lock               # 锁定依赖
├─ .python-version       # Python 版本
└─ build.ps1             # Windows 打包脚本
```

## 🧪 验证范围

Python / Web 测试可在项目根目录运行：

```powershell
uv run python -m unittest discover -s tests -p "test_*.py" -v
node tests/test_web.cjs
node tests/test_web_effects.cjs
node tests/test_web_particles.cjs
node tests/test_character_motion.cjs
```

Web 测试需要 Node.js。Windows 原生窗口嵌入测试另见 `tests/test_embedding.py`，可检查父窗口关系、缩放与宿主退出清理。

本机 Wallpaper Engine 内的最终显示尚未完成实机确认；导入后如需适配具体版本或多显示器环境，可附复现步骤提交 Issue。

## 🎨 素材来源与分辨率

- **官方原画**：Rockstar Games 的 **Jason and Lucia Robbery (With Logo)**，下载原图为 **3840 × 2160**，保留作静态回退背景。
- **动态分层**：背景补图与透明人物使用 ImageGen 辅助生成，实际分辨率为 **1672 × 941**。动态模式按屏幕尺寸缩放，不将生成图层标称为原生 4K。
- 分层提示与效果遮罩说明见 [图层素材说明](docs/图层素材说明.md)。
- [Rockstar 官方壁纸与原画页面](https://www.rockstargames.com/VI/media/artwork-wallpapers)
- 数字字体：[Anton](https://fonts.google.com/specimen/Anton)，采用 SIL Open Font License 1.1；中文调用 Windows 已安装字体，不重新分发系统字体。
- 软件使用 [PySide6 / Qt](https://www.qt.io/qt-for-python)、[PyInstaller](https://pyinstaller.org/) 与 [uv](https://docs.astral.sh/uv/)。

## 📜 许可与声明

本项目是非官方个人壁纸项目，与 Rockstar Games、Take-Two Interactive 或 Wallpaper Engine 无隶属关系。

原创程序源码按 [MIT License](LICENSE.txt) 开放；GTA VI 角色、原画、标志与商标归各自权利人所有，不属于 MIT 授权范围。生成图层用于本项目的视觉分层，不改变原有角色与商标的权利归属。字体和运行库分别遵循其原有许可，详见 [第三方说明](Licenses/第三方说明.md)。

## 🙏 感谢

- [Rockstar Games](https://www.rockstargames.com/VI)：GTA VI 与官方视觉素材
- [Wallpaper Engine](https://www.wallpaperengine.io/)：动态壁纸平台
- [Astral uv](https://docs.astral.sh/uv/)：Python 项目与依赖管理

### Web 粒子设置

在 Wallpaper Engine 属性面板中可调整“显示漂浮粒子”、数量（0–64）、亮度（0–100%）和移动速度（0–300%，0 为静止）。默认 64 个、85% 亮度、100% 速度，保持与 EXE 默认效果一致。属性定义位于 `web/project.json` 的 `general.properties`；关闭粒子、数量或亮度设为 0 时会停止粒子绘制与动画循环。

### Web 人物轻微动作

在 Wallpaper Engine 属性中开启“人物轻微动作（手臂、头发、衣服）”，用“人物动作幅度（%）”调节，默认 70%。动作使用现有人物透明图的局部连续形变，包含手臂微摆、发梢飘动和衣料起伏；面部和双腿固定，与鼠标视差叠加。幅度设为 0 或关闭动态总开关时恢复原图。宿主暂停、桌面隐藏或启用系统减少动态偏好时停止动画。

仅 Web 版使用此效果；浏览器不支持 WebGL 时自动使用原静态人物图层。渲染使用单张纹理，画布上限 1920×1080，不生成逐帧图片或视频。它是 2D 局部形变，不是骨骼动画或新的角色姿势。

Web 版已发布到 [Steam 创意工坊](https://steamcommunity.com/sharedfiles/filedetails/?id=3820814173)。本次人物动作更新已同步本地项目；创意工坊下载内容以该页面最近更新时间为准。

### 本地人物动画兼容修复（v1.4.1）

人物自动动作独立于鼠标持续播放；额外鼠标视差默认关闭。使用 `character-texture.js` 内嵌同一张透明 PNG，避免 `file://` 的图片源被拒绝上传到 WebGL。准备工具自动生成该脚本，无需关闭浏览器安全功能或启动本地服务器。已实测 file 协议下的纹理加载、鼠标静止时相位推进、鼠标移动时整体偏移为 0、暂停和恢复。人物动作默认幅度为 70%，可在 Wallpaper Engine 属性中调整。
