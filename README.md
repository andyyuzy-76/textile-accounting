# 🏠 家纺四件套记账系统

简单易用的家纺销售记账工具，专为四件套销售设计。

> 当前产品主线为 **Flet 版**（`accounting_flet.py`）；`accounting_gui.py` 进入 **legacy 维护态**，仅保留兼容与过渡用途。

## 功能特点

- ✅ **多商品录入** - 一次录入多个不同单价的商品
- 🔄 **退货管理** - 支持部分退货，关联原购买记录
- 📊 **树形显示** - 购买和退货记录父子关系一目了然
- 📈 **统计分析** - 日/月/年度销售统计
- 📥 **数据导入导出** - 支持CSV和Excel格式
- 🧾 **小票打印** - 支持58mm热敏打印机，可预览和打印
- 🔄 **自动升级** - 检测新版本一键更新
- ☁ **云端备份（Flet 版）** - WebDAV 手动/自动备份、上传校验、历史恢复

## 安装使用

### 方式一：直接运行 Python 脚本（推荐 Flet 版）

```bash
# 需要 Python 3.10+
pip install -r requirements.txt
python accounting_flet.py
```

`requirements.txt` 已锁定 Flet 0.81.0 —— Flet 的组件 API 在小版本之间会变动，随意升级可能导致界面报错。Excel 导入、打印机枚举等能力是可选依赖，文件内有注释说明。

### 方式二：运行 legacy Tk 版（仅维护，不再作为主线功能入口）

```bash
pip install -r requirements.txt
python accounting_gui.py
```

### 方式三：下载打包版本

从 [Releases](https://github.com/andyyuzy-76/textile-accounting/releases) 下载最新版本的exe文件。

## 快捷键

- `Ctrl+Enter` - 提交记录
- `F5` - 刷新显示
- 右键菜单 - 编辑/退货/删除/打印

## 小票打印

### 打印设置
点击底部工具栏的「🖨️ 打印设置」按钮，可以设置：

**打印机设置：**
- 🖨️ **选择打印机** - 选择系统已安装的打印机（或使用默认打印机）
- 📏 **纸张宽度** - 支持58mm和80mm两种宽度
- ⚡ **自动打印** - 开启后销售/退货成功后自动打印小票

**店铺信息：**
- 店铺名称、地址、电话
- 小票底部自定义文字

**实时预览：**
- 预览按钮可实时查看小票效果
- 根据纸张宽度自动调整排版

### 如何打印
1. **销售/退货后打印** - 添加记录成功后，点击「🖨️ 打印小票」按钮
2. **历史记录打印** - 在记录列表中右键点击记录，选择「🖨️ 打印小票」
3. **预览模式** - 可以先预览小票，确认无误后再打印或保存

### 支持打印机
- ✅ Windows系统打印机（USB/网络/蓝牙）
- ✅ 58mm/80mm热敏小票打印机
- ✅ 普通喷墨/激光打印机（A4纸打印）
- ✅ 支持打印预览
- ✅ 支持保存为文本文件

### 设置保存
- 所有设置自动保存到 `printer_settings.json`
- 设置将在下次启动时自动加载
- 数据目录：`C:\Users\用户名\.accounting-tool\`

## 云端备份（Windows Flet 版）

1. 运行 `python accounting_flet.py`，或双击源码目录中的 `记账系统-GUI.bat`。
2. 点击顶部云朵图标，或「系统设置 → 云端备份」。
3. 填写网盘服务商提供的 **HTTPS WebDAV 地址、NAS / WebDAV 账号和应用密码**，并设置便于识别的 **账本名称、本机名称**。账本编号和电脑编号自动生成，修改名称不改变编号。地址应指向已存在的目录，应用会在其中创建 `textile-accounting/` 子目录。
4. 点击「测试连接」确认目录可访问，再点击「立即备份」上传并下载校验。测试连接会创建子目录；测试、备份、刷新历史都会保存当前填写的设置。
5. 按需开启「保存账目或设置后自动备份」，点击「保存设置」。默认关闭；开启后约 5 秒执行，连续保存会合并，内容未改变时跳过上传。断网后在下次保存或启动时重试，请等待备份完成再关闭程序。

**备份内容：** 账目（含商品明细、退货关联、备注、客户信息）、客户列表和打印设置，以及账本编号/名称、来源电脑编号/名称、备份使用的 NAS 账号。来源信息与账目一起参与 SHA-256 校验；云端保留各次独立版本。每份新备份另有一个同名 `.meta.json` 小型来源索引，刷新历史只读索引，无需下载全部账目；手动清理时一并删除主 JSON 和对应索引。备份文件本身未加密，请使用自己的私有目录。WebDAV 密码不进入备份，使用 Windows DPAPI 加密保存在本机，仅当前 Windows 用户可解密；换电脑需重新填写应用密码。

**恢复：** 新电脑填写同一 WebDAV 目录及有权限的 NAS 账号，点击「刷新历史」。列表显示账本、来源电脑、时间和记录数，选中后可查看完整编号和 NAS 账号；点击「恢复所选备份」后，会再次按实际下载并校验的文件显示来源信息。确认后替换全部账目和打印/客户设置，并沿用备份的账本编号和名称，保留本机的电脑编号、名称和网盘登录配置。原始本地文件及账本身份先保存在数据目录的 `backups/before-restore-日期时间/`，写入失败时尝试一起回滚。旧版备份仍可恢复；没有来源信息的备份明确显示“来源未记录”，恢复后归入当前账本。建议恢复前先「立即备份」当前数据。

**账号与权限：** 当前使用 NAS / WebDAV 账号登录服务器，没有独立的软件注册登录。账本编号和来源标签用于识别备份，不代替访问权限；不同 NAS 账号若有同一目录的权限，仍可看到该目录的备份。需要隔离的账本应在 NAS 上配置各自的私有目录和权限。

数据目录为 `%USERPROFILE%\.accounting-tool\`，配置文件为 `cloud_backup.json`，账本及本机身份保存在 `backup_identity.json`，上次成功备份状态为 `cloud_backup_state.json`。当前功能不新增第三方依赖。已有 exe 可通过「检查更新」获取新功能；自行打包可运行 `build_flet.bat`。从 v1.15.8 或更早的源码版升级时，请先使用 `git pull` 获取新增模块，再重新启动。

## 自动更新与国内网络

「检查更新」读取仓库中的 `version.json`，更新包从 GitHub Releases 下载。由于国内网络对 `raw.githubusercontent.com` 和 `github.com` 的访问不稳定，更新模块做了两层兜底：

**清单读取顺序**（任一成功即停止）
1. jsDelivr CDN：`cdn.jsdelivr.net/gh/<repo>@main/version.json`
2. GitHub raw：`raw.githubusercontent.com`
3. Releases API：只读取 `tag_name` 和资产名（`api.github.com` 通常可直连）

**更新包下载顺序**
1. `version.json` 中 `download_mirrors` 配置的镜像地址（可选）
2. GitHub 官方 `browser_download_url`

镜像只影响下载地址，文件大小和 SHA-256 摘要始终取自 GitHub Releases API，校验逻辑不放松。如果需要自建加速，在 `version.json` 里加上镜像前缀即可，无需改代码：

```json
"download_mirrors": [
  "https://your-cdn.example.com/textile/",
  "https://your-cdn.example.com/d/{name}"
]
```

两种写法都支持：以 `/` 结尾的目录前缀会自动拼接文件名；带 `{name}` / `{url}` 占位符的模板会分别替换为文件名和 GitHub 原始下载地址。

更新失败时不会影响当前程序：更新包先下载到数据目录、按 SHA-256 校验，再在同目录暂存并原子替换，替换失败会自动回退旧版本，日志写在 `%USERPROFILE%\.accounting-tool\update\`。

## 验证与回归

**环境准备**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

**执行验证**

```bash
python -m pytest tests/app_core tests/smoke -q
python -m py_compile accounting_flet.py accounting_gui.py import_csv.py import_excel.py
```

仓库已配置 GitHub Actions（`.github/workflows/ci.yml`），每次推送 `main` 或提交 PR 会在 Windows 上对 Python 3.10 / 3.12 跑一遍语法检查和全部测试。

- `tests/app_core`：共享存储、记录服务、导入解析、打印设置、WebDAV 备份与恢复回滚（使用本地模拟服务）
- `tests/smoke`：Flet 入口烟雾测试
- `test_flet.py`：仅保留为手工调试入口，不再参与阻塞式自动测试

## Windows 客户端发布

1. 同步更新 `version.json`、`accounting_flet.py` 中的 `VERSION` 及版本说明，确保 `exe_asset_name` 为 `TextileAccounting_v版本号.exe`。
2. 推送到 `main` 后，在 GitHub Actions 手动运行 **Release Windows client**。流程在 Windows / Python 3.12 上安装锁定依赖，执行全部测试，打包单文件 EXE，并检查内置版本清单、Flet 运行时及启动窗口。
3. 测试和打包全部成功后，流程创建对应标签和 **草稿 Release**，上传 EXE、`version.json` 与 `SHA256SUMS.txt`；确认资产完整后再发布草稿并设为最新版本。草稿不会被客户端当作可下载更新。
4. 正式发布后，已有 EXE 可在「系统设置 → 检查更新」中升级，无需卸载。账目数据目录不参与打包，不会随程序更新被覆盖；重要账目仍建议先备份。

发布使用 `requirements-build.txt` 固定构建工具和 Excel、打印依赖；不再恢复 legacy Tk 版发布流程。

## 数据存储

数据保存在用户目录下：
- Windows: `C:\Users\用户名\.accounting-tool\records.json`

## 版本历史

### v1.15.15
- 🐛 月度统计与今日统计统一按商品明细分别累计销售、退货，修正混合单及零净数量/金额时的漏计
- 📊 同步修正月报每日明细和销售平均单价，继续兼容无商品明细的旧记录
- 📝 统一界面、版本清单及文档版本，明确 Python 3.10+、Flet 0.81.0
- ✅ 增加版本一致性、混合单、历史记录及月份切换回归测试
- 📦 新增 Windows 自动构建与草稿发布流程，包含此前源码版 v1.15.14 的更新下载改进

### v1.15.14（源码更新，未单独发布 EXE）
- 🔄 自动更新适配国内网络
  - 版本清单改为 jsDelivr → GitHub raw → Releases API 三级回退
  - 更新包下载支持 `download_mirrors` 自定义镜像，并自动重试
  - 下载改为流式写入，降低大文件中断概率
- 🐛 修复更新助手在配置文件损坏时二次抛异常、错误提示弹不出来的问题
- 🏗 补齐工程基建：`LICENSE`、`requirements.txt`、`requirements-dev.txt`、GitHub Actions CI
- 📝 README 补充自动更新说明、开发环境准备，版本历史与 Releases 对齐

### v1.15.13
- 🐛 修复自动更新后临时目录无法清理的警告弹窗
  - 更新助手就绪后正常关闭窗口，等待窗口进程退出并释放临时文件
  - 保留同路径替换、更新包校验和启动失败回退流程

### v1.15.12
- 🐛 改进云备份身份与账号校验的错误提示

### v1.15.11
- 🐛 修复更新后未替换程序文件、未自动重启的问题

### v1.15.10
- ✨ 云端备份按账本编号和来源电脑识别，备份历史展示来源信息

### v1.15.9
- ✨ 新增云端备份（WebDAV 手动/自动备份、上传校验、历史恢复）
- ✨ 新增销售退货开关

> 1.15.0 至 1.15.8 的变更请查阅 [Releases](https://github.com/andyyuzy-76/textile-accounting/releases)。

### 早期版本（0.x）

#### v0.7
- 🐛 修复自动更新按钮显示问题

#### v0.6
- 📝 优化小票打印格式

#### v0.5
- 🐛 修复自动更新文件名问题

#### v0.4
- 📝 优化小票打印格式，添加紧凑模式

#### v0.3
- ✨ 新增软件内自动更新功能
  - 一键下载并自动安装新版本
  - 支持进度显示
  - 自动备份旧版本
  - 自动重启到新版本
- 🔄 改进更新检测机制
  - 自动识别EXE文件
  - 显示自动更新按钮（仅EXE版本）

#### v0.2
- ✨ 新增小票打印功能
  - 支持58mm热敏打印机
  - 支持打印预览
  - 自定义店铺信息
  - 销售/退货后可直接打印
- 📝 右键菜单新增"打印小票"选项

#### v0.1
- 初始版本
- 多商品录入
- 部分退货功能
- 树形显示购买和退货关系
- 系统设置和升级检查

## 开源协议

本项目采用 [MIT License](LICENSE)。
