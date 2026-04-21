# Legacy Tk 归档说明

本目录用于保存已退出主发布流程的 Tk / 旧版打包资产。

## 当前状态

- `specs/`：历史 Tk / 旧版本 PyInstaller spec 文件归档
- `cli/accounting_cli.py`：旧命令行主程序归档
- `docs/使用说明-GUI.md`：旧版 Tk 使用说明归档
- `accounting_gui.py`：仍保留在仓库中，仅作 legacy 兼容参考

## 现行主线

- 运行入口：`python accounting_flet.py`
- 打包入口：`build_flet.bat`
- 默认发布方向：Flet

如无特殊兼容需求，请不要从本目录恢复旧打包流程。
