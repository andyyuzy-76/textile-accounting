# 🏠 家纺四件套记账系统

简单易用的家纺销售记账工具，专为四件套销售设计。

## 功能特点

- ✅ **多商品录入** - 一次录入多个不同单价的商品
- 🔄 **退货管理** - 支持部分退货，关联原购买记录
- 📊 **树形显示** - 购买和退货记录父子关系一目了然
- 📈 **统计分析** - 日/月/年度销售统计
- 📥 **数据导入导出** - 支持CSV和Excel格式
- 🔄 **自动升级** - 检测新版本一键更新

## 安装使用

### 方式一：直接运行Python脚本

```bash
# 需要Python 3.6+
python accounting_gui.py
```

### 方式二：下载打包版本

从 [Releases](https://github.com/andyyuzy-76/textile-accounting/releases) 下载最新版本的exe文件。

## 快捷键

- `Ctrl+Enter` - 提交记录
- `F5` - 刷新显示
- 右键菜单 - 编辑/退货/删除

## 数据存储

数据保存在用户目录下：
- Windows: `C:\Users\用户名\.accounting-tool\records.json`

## 版本历史

### v0.1
- 初始版本
- 多商品录入
- 部分退货功能
- 树形显示购买和退货关系
- 系统设置和升级检查

## 开源协议

MIT License
