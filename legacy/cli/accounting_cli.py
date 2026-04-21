#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
家纺四件套记账工具
功能：记录每日进货/销售情况
作者：AI Assistant
日期：2026-02-06
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys

class AccountingTool:
    def __init__(self, data_file: Optional[str] = None):
        """初始化记账工具"""
        if data_file is None:
            # 默认存储在用户目录下
            home_dir = os.path.expanduser("~")
            self.data_file = os.path.join(home_dir, ".accounting-tool", "records.json")
        else:
            self.data_file = data_file
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        
        # 加载数据
        self.records = self._load_records()
    
    def _load_records(self) -> List[Dict]:
        """加载历史记录"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_records(self):
        """保存记录到文件"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)
    
    def add_record(self, date: str, quantity: int, unit_price: float, 
                   note: str = "") -> Dict:
        """
        添加一条记录
        
        参数:
            date: 日期 (格式: YYYY-MM-DD)
            quantity: 数量（套）
            unit_price: 单价（元）
            note: 备注（可选）
        """
        # 验证日期格式
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": "日期格式错误，请使用 YYYY-MM-DD 格式"}
        
        # 自动计算总金额
        total_amount = quantity * unit_price
        
        # 创建记录
        record = {
            "id": len(self.records) + 1,
            "date": date,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_amount": total_amount,
            "note": note,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.records.append(record)
        self._save_records()
        
        return {
            "success": True,
            "record": record,
            "message": f"✅ 记录添加成功！日期: {date}, 数量: {quantity}套, 单价: ¥{unit_price:.2f}, 总金额: ¥{total_amount:.2f}"
        }
    
    def query_by_date(self, date: str) -> List[Dict]:
        """查询某一天的记录"""
        return [r for r in self.records if r["date"] == date]
    
    def query_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """查询日期范围内的记录"""
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return []
        
        return [r for r in self.records 
                if start <= datetime.strptime(r["date"], "%Y-%m-%d") <= end]
    
    def get_daily_summary(self, date: str) -> Dict:
        """获取某日汇总统计"""
        records = self.query_by_date(date)
        
        if not records:
            return {
                "date": date,
                "record_count": 0,
                "total_quantity": 0,
                "total_amount": 0.0,
                "avg_price": 0.0
            }
        
        total_quantity = sum(r["quantity"] for r in records)
        total_amount = sum(r["total_amount"] for r in records)
        avg_price = total_amount / total_quantity if total_quantity > 0 else 0
        
        return {
            "date": date,
            "record_count": len(records),
            "total_quantity": total_quantity,
            "total_amount": total_amount,
            "avg_price": avg_price
        }
    
    def get_monthly_summary(self, year_month: str) -> Dict:
        """获取某月汇总统计 (格式: YYYY-MM)"""
        try:
            year, month = map(int, year_month.split('-'))
        except:
            return {"error": "月份格式错误，请使用 YYYY-MM 格式"}
        
        month_records = [r for r in self.records 
                        if r["date"].startswith(year_month)]
        
        if not month_records:
            return {
                "year_month": year_month,
                "record_count": 0,
                "total_quantity": 0,
                "total_amount": 0.0
            }
        
        total_quantity = sum(r["quantity"] for r in month_records)
        total_amount = sum(r["total_amount"] for r in month_records)
        
        return {
            "year_month": year_month,
            "record_count": len(month_records),
            "total_quantity": total_quantity,
            "total_amount": total_amount
        }
    
    def delete_record(self, record_id: int) -> bool:
        """删除指定记录"""
        for i, record in enumerate(self.records):
            if record["id"] == record_id:
                del self.records[i]
                self._save_records()
                return True
        return False
    
    def get_all_records(self) -> List[Dict]:
        """获取所有记录（按日期倒序）"""
        return sorted(self.records, key=lambda x: x["date"], reverse=True)
    
    def export_to_csv(self, output_file: Optional[str] = None) -> str:
        """导出记录到 CSV 文件"""
        import csv
        
        if output_file is None:
            output_file = os.path.join(
                os.path.dirname(self.data_file),
                f"accounting_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
        
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            if self.records:
                writer = csv.DictWriter(f, fieldnames=self.records[0].keys())
                writer.writeheader()
                writer.writerows(self.records)
        
        return output_file


def print_menu():
    """打印菜单"""
    print("\n" + "="*50)
    print("🏠 家纺四件套记账工具")
    print("="*50)
    print("1. 📥 添加今日记录")
    print("2. 📅 查询某日记录")
    print("3. 📊 查询日期范围")
    print("4. 📈 查看今日统计")
    print("5. 📆 查看月度统计")
    print("6. 📋 显示所有记录")
    print("7. 🗑️  删除记录")
    print("8. 💾 导出 CSV")
    print("9. 📥 导入 Excel/CSV")
    print("10. ❌ 退出")
    print("="*50)


def main():
    """主程序"""
    tool = AccountingTool()
    
    print("\n🏠 欢迎使用家纺四件套记账工具！")
    print(f"💾 数据文件位置: {tool.data_file}")
    
    while True:
        print_menu()
        choice = input("\n请选择操作 (1-10): ").strip()
        
        if choice == "1":
            # 添加记录
            print("\n📥 添加记录")
            date = input("日期 (直接回车使用今天): ").strip()
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
            
            try:
                quantity = int(input("数量（套）: "))
                unit_price = float(input("单价（元）: "))
                note = input("备注（可选）: ").strip()
                
                result = tool.add_record(date, quantity, unit_price, note)
                print(f"\n{result['message']}")
            except ValueError:
                print("\n❌ 输入错误：数量和单价必须是数字")
        
        elif choice == "2":
            # 查询某日
            print("\n📅 查询某日记录")
            date = input("日期 (YYYY-MM-DD): ").strip()
            records = tool.query_by_date(date)
            
            if records:
                print(f"\n📌 {date} 的记录:")
                print("-" * 60)
                for r in records:
                    print(f"  ID: {r['id']} | 数量: {r['quantity']}套 | "
                          f"单价: ¥{r['unit_price']:.2f} | 金额: ¥{r['total_amount']:.2f}")
                    if r['note']:
                        print(f"  备注: {r['note']}")
                    print()
                
                # 显示汇总
                summary = tool.get_daily_summary(date)
                print("-" * 60)
                print(f"  合计: {summary['total_quantity']}套 | "
                      f"总金额: ¥{summary['total_amount']:.2f} | "
                      f"均价: ¥{summary['avg_price']:.2f}")
            else:
                print(f"\n📭 {date} 没有记录")
        
        elif choice == "3":
            # 查询日期范围
            print("\n📊 查询日期范围")
            start = input("开始日期 (YYYY-MM-DD): ").strip()
            end = input("结束日期 (YYYY-MM-DD): ").strip()
            records = tool.query_by_date_range(start, end)
            
            if records:
                print(f"\n📌 {start} 至 {end} 的记录:")
                print("-" * 60)
                total_qty = 0
                total_amt = 0.0
                for r in records:
                    print(f"  {r['date']} | 数量: {r['quantity']}套 | "
                          f"金额: ¥{r['total_amount']:.2f}")
                    total_qty += r['quantity']
                    total_amt += r['total_amount']
                print("-" * 60)
                print(f"  合计: {total_qty}套 | 总金额: ¥{total_amt:.2f}")
            else:
                print(f"\n📭 该日期范围没有记录")
        
        elif choice == "4":
            # 今日统计
            date = datetime.now().strftime("%Y-%m-%d")
            summary = tool.get_daily_summary(date)
            
            print(f"\n📈 {date} 统计:")
            print("-" * 40)
            print(f"  记录数: {summary['record_count']} 条")
            print(f"  总数量: {summary['total_quantity']} 套")
            print(f"  总金额: ¥{summary['total_amount']:.2f}")
            print(f"  平均单价: ¥{summary['avg_price']:.2f}")
        
        elif choice == "5":
            # 月度统计
            print("\n📆 月度统计")
            month = input("月份 (YYYY-MM): ").strip()
            if not month:
                month = datetime.now().strftime("%Y-%m")
            
            summary = tool.get_monthly_summary(month)
            
            print(f"\n📈 {month} 月度统计:")
            print("-" * 40)
            print(f"  记录数: {summary['record_count']} 条")
            print(f"  总数量: {summary['total_quantity']} 套")
            print(f"  总金额: ¥{summary['total_amount']:.2f}")
        
        elif choice == "6":
            # 显示所有记录
            records = tool.get_all_records()
            
            if records:
                print(f"\n📋 所有记录（共 {len(records)} 条）:")
                print("-" * 70)
                print(f"{'ID':<5} {'日期':<12} {'数量':<8} {'单价':<10} {'金额':<10} {'备注'}")
                print("-" * 70)
                for r in records[:50]:  # 最多显示50条
                    note = r['note'][:15] + "..." if len(r['note']) > 15 else r['note']
                    print(f"{r['id']:<5} {r['date']:<12} {r['quantity']:<8} "
                          f"¥{r['unit_price']:<9.2f} ¥{r['total_amount']:<9.2f} {note}")
                if len(records) > 50:
                    print(f"\n... 还有 {len(records) - 50} 条记录")
            else:
                print("\n📭 暂无记录")
        
        elif choice == "7":
            # 删除记录
            print("\n🗑️  删除记录")
            try:
                record_id = int(input("请输入要删除的记录 ID: "))
                if tool.delete_record(record_id):
                    print(f"✅ 记录 #{record_id} 已删除")
                else:
                    print(f"❌ 未找到记录 #{record_id}")
            except ValueError:
                print("❌ ID 必须是数字")
        
        elif choice == "8":
            # 导出 CSV
            output_file = tool.export_to_csv()
            print(f"\n💾 数据已导出到: {output_file}")
            print("✅ 可以用 Excel 打开查看")
        
        elif choice == "9":
            # 导入 CSV
            print("\n📥 导入 Excel/CSV 数据")
            print("💡 提示: 将 Excel 另存为 CSV 格式后再导入")
            print("      支持的列名: 日期、数量、单价、备注")
            
            file_path = input("\n请输入 CSV 文件路径: ").strip().strip('"').strip("'")
            
            if file_path:
                try:
                    # 动态导入导入模块
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    from import_csv import import_data
                    
                    result = import_data(file_path, tool)
                    
                    if result["success"]:
                        print(f"\n✅ 导入完成！成功: {result['imported']} 条")
                        if result.get('failed', 0) > 0:
                            print(f"⚠️  失败: {result['failed']} 条")
                    else:
                        print(f"\n❌ 导入失败: {result.get('error', result.get('message', '未知错误'))}")
                except Exception as e:
                    print(f"\n❌ 导入出错: {str(e)}")
            else:
                print("\n❌ 未输入文件路径")
        
        elif choice == "10":
            print("\n👋 感谢使用，再见！")
            break
        
        else:
            print("\n❌ 无效选择，请重新输入")
        
        input("\n按回车键继续...")


if __name__ == "__main__":
    main()
