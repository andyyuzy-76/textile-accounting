#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel/CSV 数据导入工具（轻量版）
无需安装 pandas，使用标准库 csv 模块
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional


def parse_date(date_str: str) -> Optional[str]:
    """解析各种日期格式"""
    if not date_str or not date_str.strip():
        return None
    
    date_str = str(date_str).strip()
    
    # 尝试多种日期格式
    date_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y年%m月%d日",
        "%Y.%m.%d",
        "%d.%m.%Y"
    ]
    
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except:
            continue
    
    # 尝试 Excel 序列号格式（如 44500）
    try:
        excel_date = int(float(date_str))
        if 1 <= excel_date <= 50000:  # Excel 日期的合理范围
            parsed = datetime(1899, 12, 30) + timedelta(days=excel_date)
            return parsed.strftime("%Y-%m-%d")
    except:
        pass
    
    return None


def parse_number(value: str) -> float:
    """解析数字，处理各种格式"""
    if not value:
        return 0.0
    
    # 移除可能的货币符号和逗号
    cleaned = str(value).replace('¥', '').replace('元', '').replace(',', '').replace(' ', '').strip()
    
    try:
        return float(cleaned)
    except:
        return 0.0


def detect_columns(headers: List[str]) -> Dict[str, int]:
    """
    自动识别列索引
    返回列名到索引的映射
    """
    column_mapping = {}
    headers_lower = [h.lower().strip() for h in headers]
    
    # 日期列
    date_keywords = ['日期', 'date', '时间', 'time']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in date_keywords):
            column_mapping['date'] = i
            break
    
    # 数量列
    quantity_keywords = ['数量', 'quantity', '套数', '件数', '套', 'qty']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in quantity_keywords):
            column_mapping['quantity'] = i
            break
    
    # 单价列
    price_keywords = ['单价', 'price', 'unit', '价格', '单价(元)']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in price_keywords):
            column_mapping['unit_price'] = i
            break
    
    # 备注列
    note_keywords = ['备注', 'note', '说明', '描述', 'notes', '客户']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in note_keywords):
            column_mapping['note'] = i
            break
    
    return column_mapping


def read_csv_file(file_path: str) -> tuple:
    """读取 CSV 文件"""
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, newline='') as f:
                # 检测分隔符
                sample = f.read(2048)
                f.seek(0)
                
                if ',' in sample:
                    reader = csv.reader(f)
                elif '\t' in sample:
                    reader = csv.reader(f, delimiter='\t')
                else:
                    reader = csv.reader(f)
                
                rows = list(reader)
                if rows:
                    return rows[0], rows[1:], encoding  # headers, data, encoding
        except:
            continue
    
    return None, None, None


def import_data(file_path: str, accounting_tool=None) -> Dict:
    """导入数据"""
    print(f"\n📂 正在读取文件: {file_path}")
    
    # 检查文件
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return {"success": False, "error": "文件不存在"}
    
    # 读取文件
    headers, data_rows, encoding = read_csv_file(file_path)
    
    if headers is None:
        print("❌ 无法读取文件，请检查文件编码")
        return {"success": False, "error": "无法读取文件"}
    
    print(f"✅ 成功读取（使用 {encoding} 编码）")
    print(f"📊 共 {len(data_rows)} 行数据")
    
    # 显示列名
    print(f"\n📋 检测到以下列:")
    for i, col in enumerate(headers, 1):
        print(f"   {i}. {col}")
    
    # 自动识别列
    column_mapping = detect_columns(headers)
    
    print(f"\n🔍 自动识别的列:")
    required_cols = {
        'date': '日期',
        'quantity': '数量',
        'unit_price': '单价'
    }
    
    for key, name in required_cols.items():
        if key in column_mapping:
            idx = column_mapping[key]
            print(f"   {name}: 第 {idx + 1} 列 ({headers[idx]})")
        else:
            print(f"   {name}: 未识别 ⚠️")
    
    # 手动指定缺失的列
    for key, name in required_cols.items():
        if key not in column_mapping:
            while True:
                try:
                    col_num = input(f"\n请手动输入'{name}'对应的列号 (1-{len(headers)}): ").strip()
                    idx = int(col_num) - 1
                    if 0 <= idx < len(headers):
                        column_mapping[key] = idx
                        print(f"   ✅ 已设置: {headers[idx]}")
                        break
                    else:
                        print(f"   ❌ 列号超出范围")
                except ValueError:
                    print(f"   ❌ 请输入数字")
    
    # 确认导入
    print(f"\n📊 即将导入 {len(data_rows)} 条记录")
    confirm = input("确认导入? (y/n): ").strip().lower()
    
    if confirm != 'y':
        return {"success": False, "message": "用户取消导入"}
    
    # 开始导入
    imported_records = []
    failed_records = []
    
    print(f"\n🔄 正在导入数据...")
    
    for row_idx, row in enumerate(data_rows, start=2):  # 从第2行开始（第1行是表头）
        try:
            # 检查行是否有足够列
            if len(row) < max(column_mapping.values()) + 1:
                failed_records.append({
                    "row": row_idx,
                    "reason": "列数不足",
                    "data": row
                })
                continue
            
            # 解析数据
            date_str = parse_date(row[column_mapping['date']])
            if not date_str:
                failed_records.append({
                    "row": row_idx,
                    "reason": f"日期格式无法识别: {row[column_mapping['date']]}",
                    "data": row
                })
                continue
            
            quantity = parse_number(row[column_mapping['quantity']])
            unit_price = parse_number(row[column_mapping['unit_price']])
            
            if quantity <= 0:
                failed_records.append({
                    "row": row_idx,
                    "reason": f"数量无效: {quantity}",
                    "data": row
                })
                continue
            
            if unit_price <= 0:
                failed_records.append({
                    "row": row_idx,
                    "reason": f"单价无效: {unit_price}",
                    "data": row
                })
                continue
            
            # 备注（可选）
            note = ""
            if 'note' in column_mapping:
                note_val = row[column_mapping['note']]
                if note_val:
                    note = str(note_val).strip()
            
            # 创建记录
            record = {
                "date": date_str,
                "quantity": int(quantity),
                "unit_price": float(unit_price),
                "total_amount": float(quantity * unit_price),
                "note": note
            }
            
            imported_records.append(record)
            
        except Exception as e:
            failed_records.append({
                "row": row_idx,
                "reason": f"处理错误: {str(e)}",
                "data": row
            })
    
    # 保存数据
    if imported_records:
        if accounting_tool:
            # 直接导入到 accounting_tool
            start_id = len(accounting_tool.records) + 1
            for i, record in enumerate(imported_records):
                record["id"] = start_id + i
                record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                accounting_tool.records.append(record)
            
            accounting_tool._save_records()
        else:
            # 保存为独立的导入文件
            output_file = os.path.expanduser("~/.accounting-tool/imported_data.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(imported_records, f, ensure_ascii=False, indent=2)
            print(f"\n💾 数据已保存到: {output_file}")
    
    # 保存失败记录日志
    if failed_records:
        log_file = os.path.expanduser("~/.accounting-tool/import_failed.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("导入失败的记录:\n")
            f.write("="*50 + "\n\n")
            for record in failed_records:
                f.write(f"第 {record['row']} 行\n")
                f.write(f"原因: {record['reason']}\n")
                f.write(f"数据: {record.get('data', 'N/A')}\n")
                f.write("-"*50 + "\n")
        print(f"📝 失败记录日志: {log_file}")
    
    return {
        "success": True,
        "imported": len(imported_records),
        "failed": len(failed_records),
        "records": imported_records
    }


def merge_imported_data():
    """将导入的数据合并到主记录中"""
    import_file = os.path.expanduser("~/.accounting-tool/imported_data.json")
    main_file = os.path.expanduser("~/.accounting-tool/records.json")
    
    if not os.path.exists(import_file):
        print("❌ 没有找到导入的数据文件")
        return False
    
    # 读取导入的数据
    with open(import_file, 'r', encoding='utf-8') as f:
        imported_records = json.load(f)
    
    # 读取现有记录
    existing_records = []
    if os.path.exists(main_file):
        with open(main_file, 'r', encoding='utf-8') as f:
            existing_records = json.load(f)
    
    # 分配 ID 并添加创建时间
    start_id = len(existing_records) + 1
    for i, record in enumerate(imported_records):
        record["id"] = start_id + i
        record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 合并
    existing_records.extend(imported_records)
    
    # 保存
    with open(main_file, 'w', encoding='utf-8') as f:
        json.dump(existing_records, f, ensure_ascii=False, indent=2)
    
    # 删除临时导入文件
    os.remove(import_file)
    
    print(f"✅ 成功合并 {len(imported_records)} 条记录")
    return True


def main():
    """主程序"""
    print("="*60)
    print("📥 Excel/CSV 数据导入工具")
    print("="*60)
    print("\n支持的文件格式:")
    print("  • CSV (.csv) - 推荐")
    print("  • Excel 导出为 CSV")
    print("\n使用步骤:")
    print("  1. 将 Excel 另存为 CSV 格式")
    print("  2. 运行此工具导入")
    print("  3. 检查导入结果")
    print()
    
    # 检查是否有待合并的数据
    import_file = os.path.expanduser("~/.accounting-tool/imported_data.json")
    if os.path.exists(import_file):
        print("⚠️  检测到之前导入但未合并的数据")
        merge = input("是否先合并之前的数据? (y/n): ").strip().lower()
        if merge == 'y':
            if merge_imported_data():
                print("✅ 数据合并完成\n")
    
    # 获取文件路径
    file_path = input("请输入 CSV 文件路径: ").strip()
    file_path = file_path.strip('"').strip("'")
    
    # 如果只有文件名，尝试在桌面和下载文件夹查找
    if not os.path.dirname(file_path):
        desktop = os.path.expanduser("~/Desktop")
        downloads = os.path.expanduser("~/Downloads")
        
        for folder in [desktop, downloads, os.getcwd()]:
            full_path = os.path.join(folder, file_path)
            if os.path.exists(full_path):
                file_path = full_path
                print(f"   ✅ 在 {folder} 找到文件")
                break
    
    # 导入数据
    result = import_data(file_path)
    
    # 显示结果
    print("\n" + "="*60)
    if result["success"]:
        print(f"✅ 导入完成!")
        print(f"   成功: {result['imported']} 条")
        if result.get('failed', 0) > 0:
            print(f"   失败: {result['failed']} 条")
        
        if result['imported'] > 0:
            merge = input("\n是否立即合并到主记账系统? (y/n): ").strip().lower()
            if merge == 'y':
                if merge_imported_data():
                    print("\n🎉 数据已成功导入记账系统！")
                    print("   现在可以运行 'python accounting.py' 查看")
    else:
        print(f"❌ 导入失败: {result.get('error', result.get('message', '未知错误'))}")
    
    print("="*60)


if __name__ == "__main__":
    main()
