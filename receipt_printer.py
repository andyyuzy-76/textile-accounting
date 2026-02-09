#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小票打印模块
支持58mm热敏打印机
"""

import os
import sys
import tempfile
from datetime import datetime
from typing import List, Dict, Optional

class ReceiptPrinter:
    """小票打印机类"""
    
    def __init__(self):
        # 58mm打印机纸张宽度约48个英文字符或24个中文字符
        self.receipt_width = 32  # 字符宽度，可动态修改
        self.shop_name = "家纺四件套"
        self.shop_address = ""
        self.shop_phone = ""
        self.header_text = ""
        self.footer_text = "谢谢惠顾，欢迎下次光临！"
    
    def set_shop_info(self, name: str = "", address: str = "", phone: str = ""):
        """设置店铺信息"""
        if name:
            self.shop_name = name
        if address:
            self.shop_address = address
        if phone:
            self.shop_phone = phone
    
    def format_receipt(self, record: Dict, compact: bool = True, return_records: list = None) -> str:
        """
        格式化小票内容
        
        参数:
            record: 记录字典，包含 date, items, total_amount, quantity, note 等
            compact: 是否使用紧凑模式（默认True，适合58mm小票一张纸）
            return_records: 关联的退货记录列表（可选）
        
        返回:
            格式化后的小票文本
        """
        if compact:
            return self._format_compact_receipt(record, return_records)
        else:
            return self._format_standard_receipt(record, return_records)
    
    def _format_compact_receipt(self, record: Dict, return_records: list = None) -> str:
        """紧凑格式小票 - 适合76mm热敏纸一张打印，左对齐充分利用纸张宽度"""
        lines = []
        # 76mm纸张实际可用宽度约44个字符（中文占2字符）
        width = 44
        
        # 店铺名称（左对齐，不居中）
        lines.append(self.shop_name[:16])  # 限制长度
        
        # 小票类型 + 单号（一行）
        is_return = record.get('type') == 'return' or record.get('quantity', 0) < 0
        receipt_type = "退" if is_return else "销"
        record_id = record.get('id', 0)
        lines.append(f"【{receipt_type}】#{record_id}")
        
        # 日期时间（显示在一行）
        date = record.get('date', datetime.now().strftime("%Y-%m-%d"))
        created_at_raw = record.get('created_at', datetime.now().strftime("%H:%M:%S"))
        # 兼容created_at存储完整日期时间的情况，提取时间部分
        if ' ' in created_at_raw:
            created_at = created_at_raw.split(' ')[1]
        else:
            created_at = created_at_raw
        lines.append(f"{date} {created_at}")
        
        # 分隔线（一排）
        lines.append("-" * 22)
        
        # 商品明细 - 超紧凑格式
        items = record.get('items', [])
        if not items:
            # 兼容旧数据格式
            qty = abs(record.get('quantity', 0))
            price = record.get('unit_price', 0)
            subtotal = qty * price
            lines.append(f"{qty}套 @ ¥{price:.0f} = ¥{subtotal:.0f}")
        else:
            for i, item in enumerate(items, 1):
                qty = abs(item.get('quantity', 0))
                price = item.get('unit_price', 0)
                subtotal = qty * price
                # 76mm纸张可以更宽松：序号.数量套@单价=金额
                lines.append(f"{i}.{qty}套@¥{price:.0f}=¥{subtotal:.0f}")
        
        # 合计行
        total_amount = abs(record.get('total_amount', 0))
        total_qty = abs(record.get('quantity', 0))
        lines.append("-" * 22)
        lines.append(f"共{total_qty}套 ¥{total_amount:.0f}")
        
        # 如果有退货记录，显示退货明细和净额
        if return_records:
            lines.append("")
            lines.append("【退货明细】")
            return_total = 0
            return_qty_total = 0
            for i, ret in enumerate(return_records, 1):
                ret_qty = abs(ret.get('quantity', 0))
                ret_amount = abs(ret.get('total_amount', 0))
                return_qty_total += ret_qty
                return_total += ret_amount
                lines.append(f"退{i}.{ret_qty}套=¥{ret_amount:.0f}")
            lines.append("-" * 22)
            lines.append(f"退货合计:{return_qty_total}套 ¥{return_total:.0f}")
            # 净额
            net_amount = total_amount - return_total
            lines.append(f"实付金额:¥{net_amount:.0f}")
        
        # 备注（超短）
        note = record.get('note', '')
        if note:
            note_text = note[:10] + ".." if len(note) > 10 else note
            lines.append(f"注:{note_text}")
        
        # 电话（如果有）
        if self.shop_phone:
            lines.append(f"{self.shop_phone}")
        
        # 底部文字（左对齐）
        footer = self.footer_text[:12] if len(self.footer_text) > 12 else self.footer_text
        lines.append(footer)
        
        return "\n".join(lines)
    
    def _format_standard_receipt(self, record: Dict) -> str:
        """标准格式小票 - 更美观但占用更多纸张"""
        lines = []
        width = self.receipt_width
        
        # 分隔线
        separator = "=" * width
        separator_light = "-" * width
        
        # 店铺名称（居中）
        lines.append("")
        lines.append(self._center_text(self.shop_name, width))
        lines.append(separator)
        
        # 小票类型
        is_return = record.get('type') == 'return' or record.get('quantity', 0) < 0
        receipt_type = "【退货单】" if is_return else "【销售单】"
        lines.append(self._center_text(receipt_type, width))
        lines.append("")
        
        # 单号
        record_id = record.get('id', 0)
        lines.append(f"单号: #{record_id}")
        
        # 日期时间
        date = record.get('date', datetime.now().strftime("%Y-%m-%d"))
        created_at_raw = record.get('created_at', datetime.now().strftime("%H:%M:%S"))
        # 兼容created_at存储完整日期时间的情况，提取时间部分
        if ' ' in created_at_raw:
            created_at = created_at_raw.split(' ')[1]
        else:
            created_at = created_at_raw
        lines.append(f"日期: {date} {created_at}")
        lines.append(separator_light)
        
        # 商品明细
        lines.append(self._format_line("商品", "金额", width))
        lines.append(separator_light)
        
        items = record.get('items', [])
        if not items:
            # 兼容旧数据格式
            qty = abs(record.get('quantity', 0))
            price = record.get('unit_price', 0)
            lines.append(f"四件套 x{qty} @¥{price:.2f}")
        else:
            for i, item in enumerate(items, 1):
                qty = abs(item.get('quantity', 0))
                price = item.get('unit_price', 0)
                subtotal = qty * price
                
                # 商品名称行
                lines.append(f"商品{i}: 四件套")
                # 数量和单价行
                lines.append(f"  x{qty} @¥{price:.2f} = ¥{subtotal:.2f}")
        
        lines.append(separator_light)
        
        # 合计
        total_amount = abs(record.get('total_amount', 0))
        total_qty = abs(record.get('quantity', 0))
        lines.append(self._format_line(f"合计: {total_qty}套", f"¥{total_amount:.2f}", width))
        lines.append("")
        
        # 备注
        note = record.get('note', '')
        if note:
            # 处理长备注，自动换行
            note_lines = self._wrap_text(f"备注: {note}", width)
            lines.extend(note_lines)
            lines.append("")
        
        # 分隔线
        lines.append(separator)
        
        # 底部信息
        if self.shop_phone:
            lines.append(f"电话: {self.shop_phone}")
        if self.shop_address:
            address_lines = self._wrap_text(f"地址: {self.shop_address}", width)
            lines.extend(address_lines)
        
        lines.append("")
        lines.append(self._center_text(self.footer_text, width))
        lines.append("")
        lines.append(separator)
        lines.append("")
        
        return "\n".join(lines)
    
    def _center_text(self, text: str, width: int) -> str:
        """文本居中"""
        # 计算中文字符的实际宽度
        text_width = self._get_text_width(text)
        padding = (width - text_width) // 2
        return " " * padding + text
    
    def _get_text_width(self, text: str) -> int:
        """获取文本实际宽度（中文字符算2个宽度）"""
        width = 0
        for char in text:
            if ord(char) > 127:  # 中文字符
                width += 2
            else:
                width += 1
        return width
    
    def _format_line(self, left: str, right: str, width: int) -> str:
        """格式化左右对齐的行"""
        left_width = self._get_text_width(left)
        right_width = self._get_text_width(right)
        spaces = width - left_width - right_width
        if spaces < 1:
            spaces = 1
        return left + " " * spaces + right
    
    def _wrap_text(self, text: str, width: int) -> List[str]:
        """文本自动换行"""
        lines = []
        current_line = ""
        current_width = 0
        
        for char in text:
            char_width = 2 if ord(char) > 127 else 1
            
            if current_width + char_width > width:
                lines.append(current_line)
                current_line = char
                current_width = char_width
            else:
                current_line += char
                current_width += char_width
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [text]
    
    def print_to_windows_printer(self, receipt_text: str, printer_name: Optional[str] = None) -> Dict:
        """
        打印到Windows打印机
        
        参数:
            receipt_text: 小票文本内容
            printer_name: 打印机名称，None则使用默认打印机
        
        返回:
            操作结果字典
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(receipt_text)
                temp_file = f.name
            
            # 使用Windows命令打印
            if printer_name:
                # 使用PowerShell指定打印机打印
                ps_command = f'Start-Process -FilePath "{temp_file}" -Verb PrintTo -ArgumentList "{printer_name}" -PassThru | ForEach-Object {{ Start-Sleep -Seconds 2; $_ }}'
                os.system(f'powershell.exe -Command "{ps_command}"')
            else:
                # 使用默认打印机
                os.system(f'notepad /p "{temp_file}"')
            
            # 清理临时文件（延迟删除，确保打印完成）
            def cleanup():
                import time
                time.sleep(5)
                try:
                    os.remove(temp_file)
                except:
                    pass
            
            import threading
            threading.Thread(target=cleanup, daemon=True).start()
            
            printer_info = f" ({printer_name})" if printer_name else ""
            return {"success": True, "message": f"打印任务已发送到打印机{printer_info}"}
            
        except Exception as e:
            return {"success": False, "message": f"打印失败: {str(e)}"}
    
    def print_to_pos_printer(self, receipt_text: str, printer_name: Optional[str] = None) -> Dict:
        """
        打印到POS热敏打印机（使用ESC/POS指令）
        
        这需要安装额外的库如 python-escpos
        """
        try:
            # 尝试使用escpos库
            from escpos.printer import Usb, Network, Windows
            
            # 这里简化处理，实际使用时需要根据打印机连接方式选择
            # p = Usb(0x0416, 0x5011)  # USB连接示例
            # 或者
            # p = Network("192.168.1.100")  # 网络打印机
            
            # 由于没有具体的打印机信息，这里返回提示
            return {
                "success": False, 
                "message": "POS打印机需要配置USB或网络参数，请使用普通打印机方式"
            }
            
        except ImportError:
            return {
                "success": False,
                "message": "未安装 python-escpos 库，请运行: pip install python-escpos"
            }
        except Exception as e:
            return {"success": False, "message": f"POS打印失败: {str(e)}"}
    
    def get_receipt_html(self, record: Dict, paper_width: int = 58) -> str:
        """
        生成小票的HTML格式（用于预览）
        
        参数:
            record: 记录字典
            paper_width: 纸张宽度（mm），支持58/76/80
        
        返回:
            HTML字符串
        """
        # 根据纸张宽度设置CSS宽度
        mm_width = paper_width
        is_return = record.get('type') == 'return' or record.get('quantity', 0) < 0
        receipt_type = "退货单" if is_return else "销售单"
        
        date = record.get('date', datetime.now().strftime("%Y-%m-%d"))
        created_at = record.get('created_at', datetime.now().strftime("%H:%M:%S"))
        record_id = record.get('id', 0)
        note = record.get('note', '')
        total_amount = abs(record.get('total_amount', 0))
        total_qty = abs(record.get('quantity', 0))
        
        # 构建商品明细HTML
        items_html = ""
        items = record.get('items', [])
        if not items:
            qty = abs(record.get('quantity', 0))
            price = record.get('unit_price', 0)
            subtotal = qty * price
            items_html += f"""
            <tr>
                <td>四件套</td>
                <td style="text-align:center">{qty}</td>
                <td style="text-align:right">¥{price:.2f}</td>
                <td style="text-align:right">¥{subtotal:.2f}</td>
            </tr>
            """
        else:
            for i, item in enumerate(items, 1):
                qty = abs(item.get('quantity', 0))
                price = item.get('unit_price', 0)
                subtotal = qty * price
                items_html += f"""
                <tr>
                    <td>商品{i}: 四件套</td>
                    <td style="text-align:center">{qty}</td>
                    <td style="text-align:right">¥{price:.2f}</td>
                    <td style="text-align:right">¥{subtotal:.2f}</td>
                </tr>
                """
        
        note_html = f"<p><strong>备注:</strong> {note}</p>" if note else ""
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: "微软雅黑", "SimHei", sans-serif;
                    font-size: 12px;
                    line-height: 1.4;
                    margin: 0;
                    padding: 10px;
                    background: #f5f5f5;
                }}
                .receipt {{
                    background: white;
                    width: {mm_width}mm;
                    min-height: 100mm;
                    margin: 0 auto;
                    padding: 10px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    border-bottom: 2px dashed #333;
                    padding-bottom: 8px;
                    margin-bottom: 8px;
                }}
                .shop-name {{
                    font-size: 16px;
                    font-weight: bold;
                    margin-bottom: 4px;
                }}
                .receipt-type {{
                    font-size: 14px;
                    color: #e74c3c;
                    font-weight: bold;
                }}
                .info {{
                    margin: 8px 0;
                    font-size: 11px;
                }}
                .info-row {{
                    display: flex;
                    justify-content: space-between;
                    margin: 2px 0;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 8px 0;
                    font-size: 11px;
                }}
                th, td {{
                    padding: 4px 2px;
                    border-bottom: 1px dotted #ccc;
                }}
                th {{
                    border-top: 1px solid #333;
                    border-bottom: 1px solid #333;
                    font-weight: bold;
                }}
                .total {{
                    border-top: 2px solid #333;
                    margin-top: 8px;
                    padding-top: 8px;
                    font-size: 13px;
                    font-weight: bold;
                    display: flex;
                    justify-content: space-between;
                }}
                .note {{
                    margin-top: 8px;
                    padding-top: 8px;
                    border-top: 1px dashed #ccc;
                    font-size: 10px;
                    word-break: break-all;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 16px;
                    padding-top: 8px;
                    border-top: 2px dashed #333;
                    font-size: 10px;
                    color: #666;
                }}
                .qrcode {{
                    text-align: center;
                    margin: 8px 0;
                }}
            </style>
        </head>
        <body>
            <div class="receipt">
                <div class="header">
                    <div class="shop-name">{self.shop_name}</div>
                    <div class="receipt-type">{receipt_type}</div>
                </div>
                
                <div class="info">
                    <div class="info-row">
                        <span>单号: #{record_id}</span>
                    </div>
                    <div class="info-row">
                        <span>日期: {date}</span>
                        <span>时间: {created_at}</span>
                    </div>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th style="text-align:left">商品</th>
                            <th style="text-align:center">数量</th>
                            <th style="text-align:right">单价</th>
                            <th style="text-align:right">金额</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
                
                <div class="total">
                    <span>合计: {total_qty}套</span>
                    <span>¥{total_amount:.2f}</span>
                </div>
                
                {f'<div class="note"><strong>备注:</strong> {note}</div>' if note else ''}
                
                <div class="footer">
                    {f'<div>电话: {self.shop_phone}</div>' if self.shop_phone else ''}
                    {f'<div>地址: {self.shop_address}</div>' if self.shop_address else ''}
                    <div style="margin-top:8px;font-weight:bold;">{self.footer_text}</div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html


def get_printer_list():
    """获取系统打印机列表"""
    printers = []
    
    try:
        if os.name == 'nt':  # Windows
            import win32print
            printers_info = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            for printer in printers_info:
                printers.append(printer[2])  # 打印机名称
        else:  # Linux/Mac
            import subprocess
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if line.startswith('printer'):
                    printer_name = line.split()[1].rstrip(':')
                    printers.append(printer_name)
    except Exception as e:
        # 如果获取失败，返回空列表
        pass
    
    return printers


if __name__ == "__main__":
    # 测试
    printer = ReceiptPrinter()
    printer.set_shop_info("测试家纺店", "某某街道123号", "13800138000")
    
    test_record = {
        "id": 1001,
        "date": "2026-02-08",
        "created_at": "14:30:25",
        "quantity": 3,
        "unit_price": 280.00,
        "total_amount": 840.00,
        "note": "客户：张女士",
        "items": [
            {"quantity": 1, "unit_price": 300.00},
            {"quantity": 2, "unit_price": 270.00}
        ]
    }
    
    receipt = printer.format_receipt(test_record)
    print(receipt)
    print("\n" + "="*50)
    print("打印机列表:", get_printer_list())
