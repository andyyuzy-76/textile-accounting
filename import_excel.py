#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel/CSV 数据导入工具
用于将以前的 Excel 记录导入到家纺记账系统中
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

from app_core.services.importers import detect_named_columns
from app_core.services.importers import parse_date as shared_parse_date
from app_core.services.importers import parse_number as shared_parse_number

def detect_columns(df: pd.DataFrame) -> Dict[str, str]:
    """自动识别列名"""
    return detect_named_columns(df.columns)


def parse_date(date_value) -> str:
    """解析各种日期格式"""
    if pd.isna(date_value):
        return None
    return shared_parse_date(date_value)


def parse_number(value) -> float:
    """解析数字，处理各种格式"""
    if pd.isna(value):
        return 0.0
    return shared_parse_number(value)


def import_from_excel(excel_file: str, accounting_tool=None) -> Dict:
    """
    从 Excel/CSV 文件导入数据
    
    参数:
        excel_file: Excel 或 CSV 文件路径
        accounting_tool: AccountingTool 实例（可选）
    """
    print(f"\n📂 正在读取文件: {excel_file}")
    
    try:
        # 根据文件扩展名选择读取方式
        file_ext = os.path.splitext(excel_file)[1].lower()
        
        if file_ext == '.csv':
            # 尝试不同的编码
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
            for encoding in encodings:
                try:
                    df = pd.read_csv(excel_file, encoding=encoding)
                    print(f"   ✅ 使用 {encoding} 编码成功读取")
                    break
                except:
                    continue
            else:
                return {"success": False, "error": "无法读取 CSV 文件，编码不支持"}
        
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(excel_file)
            print(f"   ✅ Excel 文件读取成功，共 {len(df)} 行")
        
        else:
            return {"success": False, "error": f"不支持的文件格式: {file_ext}"}
    
    except Exception as e:
        return {"success": False, "error": f"读取文件失败: {str(e)}"}
    
    # 显示列名供用户确认
    print(f"\n📊 检测到以下列:")
    for i, col in enumerate(df.columns, 1):
        print(f"   {i}. {col}")
    
    # 自动识别列
    column_mapping = detect_columns(df)
    
    print(f"\n🔍 自动识别的列:")
    print(f"   日期: {column_mapping.get('date', '未识别')}")
    print(f"   数量: {column_mapping.get('quantity', '未识别')}")
    print(f"   单价: {column_mapping.get('unit_price', '未识别')}")
    print(f"   备注: {column_mapping.get('note', '未识别')}")
    
    # 检查必需的列
    required_cols = ['date', 'quantity', 'unit_price']
    missing_cols = [col for col in required_cols if col not in column_mapping]
    
    if missing_cols:
        print(f"\n⚠️  以下必需列未能自动识别: {', '.join(missing_cols)}")
        print("\n💡 请手动指定列号:")
        
        for col_name in missing_cols:
            while True:
                try:
                    col_idx = int(input(f"   {col_name} 对应的列号 (1-{len(df.columns)}): ")) - 1
                    if 0 <= col_idx < len(df.columns):
                        column_mapping[col_name] = df.columns[col_idx]
                        break
                    else:
                        print("   ❌ 列号超出范围")
                except ValueError:
                    print("   ❌ 请输入数字")
    
    # 确认导入
    print(f"\n📋 即将导入 {len(df)} 条记录")
    confirm = input("确认导入? (y/n): ").strip().lower()
    
    if confirm != 'y':
        return {"success": False, "message": "用户取消导入"}
    
    # 开始导入
    imported_records = []
    failed_records = []
    
    print(f"\n🔄 正在导入数据...")
    
    for idx, row in df.iterrows():
        try:
            # 解析日期
            date_str = parse_date(row[column_mapping['date']])
            if not date_str:
                failed_records.append({
                    "row": idx + 2,
                    "reason": "日期格式无法识别",
                    "value": row[column_mapping['date']]
                })
                continue
            
            # 解析数量和单价
            quantity = parse_number(row[column_mapping['quantity']])
            unit_price = parse_number(row[column_mapping['unit_price']])
            
            if quantity <= 0 or unit_price <= 0:
                failed_records.append({
                    "row": idx + 2,
                    "reason": "数量或单价无效",
                    "quantity": quantity,
                    "unit_price": unit_price
                })
                continue
            
            # 解析备注（可选）
            note = ""
            if 'note' in column_mapping:
                note_value = row[column_mapping['note']]
                if pd.notna(note_value):
                    note = str(note_value).strip()
            
            # 创建记录
            record = {
                "id": 0,  # 稍后由 accounting_tool 分配
                "date": date_str,
                "quantity": int(quantity),
                "unit_price": float(unit_price),
                "total_amount": float(quantity * unit_price),
                "note": note,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            imported_records.append(record)
            
        except Exception as e:
            failed_records.append({
                "row": idx + 2,
                "reason": f"处理错误: {str(e)}"
            })
    
    # 如果提供了 accounting_tool，直接导入
    if accounting_tool and imported_records:
        start_id = len(accounting_tool.records) + 1
        for i, record in enumerate(imported_records):
            record["id"] = start_id + i
            accounting_tool.records.append(record)
        
        accounting_tool._save_records()
        print(f"\n✅ 成功导入 {len(imported_records)} 条记录")
        
        if failed_records:
            print(f"⚠️  {len(failed_records)} 条记录导入失败")
            save_failed_log(failed_records)
        
        return {
            "success": True,
            "imported": len(imported_records),
            "failed": len(failed_records),
            "records": imported_records
        }
    
    else:
        # 返回记录供外部处理
        return {
            "success": True,
            "imported": len(imported_records),
            "failed": len(failed_records),
            "records": imported_records,
            "failed_details": failed_records
        }


def save_failed_log(failed_records: List[Dict]):
    """保存导入失败的记录日志"""
    log_file = os.path.expanduser("~/.accounting-tool/import_failed.log")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("导入失败的记录:\n")
        f.write("="*50 + "\n")
        for record in failed_records:
            f.write(f"行号: {record['row']}, 原因: {record['reason']}\n")
            if 'value' in record:
                f.write(f"  值: {record['value']}\n")
            f.write("\n")
    print(f"\n📝 失败记录已保存到: {log_file}")


def main():
    """主程序"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    print("="*60)
    print("📥 Excel/CSV 数据导入工具")
    print("="*60)
    print("\n支持的文件格式:")
    print("  • Excel (.xlsx, .xls)")
    print("  • CSV (.csv)")
    print("\n支持的日期格式:")
    print("  • 2026-02-06")
    print("  • 2026/02/06")
    print("  • 2026年02月06日")
    print("  • Excel 日期序列号")
    print()
    
    # 获取文件路径
    file_path = input("请输入 Excel/CSV 文件路径: ").strip()
    
    # 去除引号（如果用户拖入文件）
    file_path = file_path.strip('"').strip("'")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        # 尝试在常见位置查找
        desktop = os.path.expanduser("~/Desktop")
        downloads = os.path.expanduser("~/Downloads")
        
        for folder in [desktop, downloads]:
            alt_path = os.path.join(folder, os.path.basename(file_path))
            if os.path.exists(alt_path):
                file_path = alt_path
                print(f"   ✅ 在 {folder} 找到文件")
                break
        else:
            print(f"❌ 文件不存在: {file_path}")
            return
    
    # 导入数据
    try:
        from accounting import AccountingTool
        tool = AccountingTool()
        result = import_from_excel(file_path, tool)
    except ImportError:
        print("⚠️  未找到 accounting 模块，将生成导入数据文件")
        result = import_from_excel(file_path)
        
        if result["success"] and result["records"]:
            # 保存为临时 JSON 文件
            output_file = os.path.expanduser("~/.accounting-tool/imported_data.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result["records"], f, ensure_ascii=False, indent=2)
            print(f"\n💾 导入数据已保存到: {output_file}")
            print("   请运行 accounting.py 并选择添加记录来导入")
    
    print("\n" + "="*60)
    if result["success"]:
        print(f"✅ 导入完成!")
        print(f"   成功: {result['imported']} 条")
        if result.get('failed', 0) > 0:
            print(f"   失败: {result['failed']} 条")
    else:
        print(f"❌ 导入失败: {result.get('error', '未知错误')}")
    print("="*60)


if __name__ == "__main__":
    from datetime import timedelta
    main()
