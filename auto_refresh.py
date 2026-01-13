#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票价格自动刷新显示工具
只保留自动刷新显示模式
"""

import requests
import time
import argparse
import sys
import re
from datetime import datetime, timedelta
import concurrent.futures

# 全局变量存储每个股票的最新价格
last_prices = {}
try:
    from wcwidth import wcswidth
except ImportError:
    # 如果没有安装wcwidth库，则定义一个简单的替代函数
    def wcswidth(s):
        """简单估算字符串显示宽度的函数"""
        width = 0
        for char in s:
            if ord(char) < 127:  # ASCII字符
                width += 1
            else:  # 假设中文或其他字符占2个位置
                width += 2
        return width


def get_ansi_stripped_length(text):
    """
    计算去除ANSI颜色代码后的字符串长度
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', text))


def format_with_color_padding(text, width, align = '>'):
    """
    格式化带颜色的文本，确保对齐正确
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    stripped_text = ansi_escape.sub('', text)
    stripped_len = wcswidth(stripped_text)
    padding_needed = max(0, width - stripped_len)

    if align == '>':
        return ' ' * padding_needed + text
    elif align == '<':
        return text + ' ' * padding_needed
    elif align == '^':
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return ' ' * left_pad + text + ' ' * right_pad
    else:
        return text


def format_column_text(text, width, align='left'):
    """
    使用wcwidth格式化列文本以实现正确的对齐
    """
    text_str = str(text)
    text_width = wcswidth(text_str)
    padding_needed = max(0, width - text_width)

    if align == 'left':
        return text_str + ' ' * padding_needed
    elif align == 'right':
        return ' ' * padding_needed + text_str
    elif align == 'center':
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return ' ' * left_pad + text_str + ' ' * right_pad
    else:
        return text_str


def get_stock_realtime_data(stock_code):
    """
    从新浪财经获取实时股票数据
    股票代码格式：000001 或 600000
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }

        # 确定市场代码并格式化股票代码
        if stock_code.startswith(('5', '6', '9')):  # 上海证券交易所
            symbol = 'sh{}'.format(stock_code)
        else:  # 深圳证券交易所
            symbol = 'sz{}'.format(stock_code)

        # 新浪财经实时数据API
        url = "http://hq.sinajs.cn/list={}".format(symbol)

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'gbk'  # 新浪财经使用GBK编码

        # 解析返回的数据
        content = response.text.strip()
        if 'var hq_str_' in content:
            # 提取数据部分
            data_str = content.split('"')[1] if '"' in content else ""
            if data_str:
                fields = data_str.split(',')

                if len(fields) >= 32:
                    name = fields[0]
                    clean_name = name

                    # 移除名称中的空格以改善对齐
                    clean_name = clean_name.replace(' ', '')

                    # 检查股票是否停牌
                    # 股票被认为停牌的条件：
                    # 1. 当前价格等于前收盘价（无波动）
                    # 2. 成交量为0（无交易）
                    # 3. 最高价和最低价等于前收盘价（当天无价格波动）
                    price = float(fields[3])
                    pre_close = float(fields[2])
                    volume = int(fields[8])
                    high = float(fields[4])
                    low = float(fields[5])

                    # 检查停牌条件
                    # 特殊情况：如果价格为0，可能表示停牌或无数据
                    is_suspended = (
                        (price == pre_close and volume == 0 and high == low and high == pre_close) or
                        (price == 0 and pre_close != 0) or  # 价格为0但前收盘价不为0（表示停牌）
                        (volume == 0 and price == pre_close)  # 无成交量且价格无变化
                    )

                    return {
                        'code': stock_code,
                        'name': clean_name,        # 清理后的股票名称
                        'pre_close': float(fields[2]), # 昨日收盘价
                        'price': float(fields[3]),   # 当前价格
                        'high': float(fields[4]),    # 今日最高价
                        'low': float(fields[5]),     # 今日最低价
                        'time': fields[31],          # 时间
                        'is_suspended': is_suspended  # 停牌状态
                    }
                else:
                    # 如果字段数量不足，尝试简化处理
                    if len(fields) >= 4:
                        name = fields[0] if fields[0] else f"Stock{stock_code}"
                        # 分析股票名称以确定是否包含类别标识符
                        clean_name = name

                        # 移除名称中的空格以改善对齐
                        clean_name = re.sub(r'\s+', '', clean_name)

                        # 对于简化处理，检查股票是否似乎已停牌
                        price = float(fields[3]) if fields[3] and fields[3] != '' else 0
                        pre_close = float(fields[2]) if len(fields) > 2 and fields[2] and fields[2] != '' else 0

                        # 简化数据的增强停牌检测
                        is_suspended = (
                            (price == pre_close and price == 0 and pre_close != 0) or  # 价格为0但前收盘价不为0
                            (price != 0 and price == pre_close) or  # 相同价格，非零
                            (price == 0 and pre_close != 0)  # 当前价格为0但前收盘价不为0
                        )

                        return {
                            'code': stock_code,
                            'name': clean_name,
                            'price': float(fields[3]) if fields[3] and fields[3] != '' else 0,
                            'pre_close': float(fields[2]) if len(fields) > 2 and fields[2] and fields[2] != '' else 0,
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'is_suspended': is_suspended  # 停牌状态
                        }

    except Exception as e:
        print(f"获取股票 {stock_code} 数据时出错: {e}")
        return None


def read_stock_list(file_path):
    """
    从文件读取股票列表，包括持有数量
    返回包含 'code' 和 'quantity' 键的字典列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        stocks = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 提取股票代码和持有数量（前两部分）
                parts = line.split()
                if parts:
                    # 提取股票代码的纯数字部分
                    code = parts[0].split('.')[0]  # 移除 .SZ 或 .SH 后缀
                    # 提取持有数量，如果未提供则默认为0
                    quantity = 0
                    if len(parts) >= 2:
                        try:
                            quantity = int(parts[1])
                        except ValueError:
                            quantity = 0  # 如果不是有效整数则默认为0
                    stocks.append({'code': code, 'quantity': quantity})

        return stocks
    except Exception as e:
        print(f"读取股票列表文件 {file_path} 时出错: {e}")
        return []


def display_stock_info(stock_info, holding_quantity=0, last_price=None):
    """格式化显示单个股票信息，包括持有数量、收益金额、趋势、最高价和最低价"""
    if stock_info:
        # 检查是否停牌
        is_suspended = stock_info.get('is_suspended', False)

        # 计算涨跌额和涨跌幅
        change = stock_info['price'] - stock_info['pre_close']
        change_pct = (change / stock_info['pre_close']) * 100

        # 如果是停牌股票，使用昨收价作为显示价格，涨跌设为0
        if is_suspended:
            display_price = stock_info['pre_close']  # 使用昨收价显示
            change = 0.0  # 涨跌额为0
            change_pct = 0.0  # 涨跌幅为0
        else:
            display_price = stock_info['price']  # 使用实际价格

        # 计算收益金额
        profit_amount = (display_price - stock_info['pre_close']) * holding_quantity

        # 计算趋势
        trend_symbol = ""
        if last_price is not None:
            if display_price > last_price:
                trend_symbol = "\033[91m↑\033[0m"  # 红色上升
            elif display_price < last_price:
                trend_symbol = "\033[92m↓\033[0m"  # 绿色下降
            else:
                trend_symbol = "\033[93m-\033[0m"  # 黄色持平
        else:
            trend_symbol = "\033[93m-\033[0m"  # 首次显示为黄色持平

        # 根据涨跌显示颜色（如果终端支持）
        change_pct_str = f"{change_pct:>+8.2f}%"
        profit_str = f"{profit_amount:>+10.2f}"

        if change > 0:
            change_pct_display = f"\033[91m{change_pct_str}\033[0m"  # 红色
            profit_display = f"\033[91m{profit_str}\033[0m"  # 红色
        elif change < 0:
            change_pct_display = f"\033[92m{change_pct_str}\033[0m"  # 绿色
            profit_display = f"\033[92m{profit_str}\033[0m"  # 绿色
        else:
            # 对于零值，使用+0.00格式以保持对齐
            change_pct_display = f"\033[93m{change_pct_str}\033[0m"  # 黄色，显示为+0.00（停牌或无变动）
            profit_display = f"\033[93m{profit_str}\033[0m"  # 黄色

        # 使用固定长度填充以确保对齐
        name = stock_info['name']

        # 限制股票名称长度以确保对齐，使用固定宽度
        name_display = name[:16]  # 限制名称长度为16个字符

        # 使用新函数格式化各列
        name_part = format_column_text(name_display, 20, 'right')
        quantity_part = format_column_text(holding_quantity, 10, 'right')
        # 确保趋势符号列宽度固定为6个字符（不包括颜色代码），右对齐，以容纳最宽的符号
        # trend_part = format_with_color_padding(trend_symbol, 6, '>')  # 趋势符号，右对齐
        trend_aligned = " " * 5 + trend_symbol
        high_part = format_column_text(f"{stock_info.get('high', 0):.2f}", 8, 'right')  # 最高价
        low_part = format_column_text(f"{stock_info.get('low', 0):.2f}", 8, 'right')  # 最低价
        price_part = format_column_text(f"{display_price:.2f}", 10, 'right')  # 使用调整后的价格显示

        # 计算涨跌百分比所需的空格数（基于非颜色版本的长度）
        pct_spaces = 12 - wcswidth(change_pct_str)
        pct_aligned = " " * max(0, pct_spaces) + change_pct_display

        # 利润金额间距
        profit_spaces = 14 - wcswidth(profit_str)
        profit_aligned = " " * max(0, profit_spaces) + profit_display

        # 格式化时间显示（仅时间，无日期）
        stock_time = stock_info.get('time', 'N/A')

        # 使用新函数格式化时间列
        time_part = format_column_text(stock_time, 10, 'right')

        print(f"{name_part} {quantity_part} {trend_aligned} {high_part} {low_part} {price_part} {pct_aligned} {profit_aligned} {time_part}")

        return profit_amount, display_price, stock_info['pre_close'] * holding_quantity  # 返回利润金额、当前价格和成本
    return 0, 0, 0  # 如果没有股票信息，返回0


def main():
    parser = argparse.ArgumentParser(description='Stock Price Display Tool')
    parser.add_argument('--list', '-l', default='stock_list.txt', help='Stock list file path')
    parser.add_argument('--interval', '-i', type=int, default=30, help='Monitoring interval in seconds (enables auto-refresh mode)')
    parser.add_argument('--sort-by-profit', '-s', action='store_true', help='Sort by profit amount (default: sort by code)')

    args = parser.parse_args()

    # 从文件读取股票列表
    stock_list = read_stock_list(args.list)

    if not stock_list:
        print(f"Stock list not found or empty: {args.list}")
        sys.exit(1)

    print(f"Start monitoring {len(stock_list)} stocks, press Ctrl+C to stop...")
    print(f"Update interval: {args.interval} seconds")
    monitor_loop(stock_list, args.interval, sort_by_profit=args.sort_by_profit)

def get_all_stock_data(stock_list):
    """并发获取所有股票数据"""
    stock_data = {}

    # 使用线程池并发获取数据
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # 提交所有任务
        future_to_code = {
            executor.submit(get_stock_realtime_data, stock_item['code']): stock_item
            for stock_item in stock_list
        }

        # 获取结果
        for future in concurrent.futures.as_completed(future_to_code):
            stock_item = future_to_code[future]
            stock_code = stock_item['code']
            holding_quantity = stock_item['quantity']

            try:
                stock_info = future.result()
                stock_data[stock_code] = {
                    'info': stock_info,
                    'quantity': holding_quantity
                }
            except Exception as e:
                print(f"获取股票 {stock_code} 数据时出错: {e}")
                stock_data[stock_code] = {
                    'info': None,
                    'quantity': holding_quantity
                }

    return stock_data


def monitor_loop(stock_list, interval, sort_by_profit=True):
    """循环监控模式"""
    try:
        while True:
            # 清屏（在支持的终端上）
            import os
            os.system('clear' if os.name == 'posix' else 'cls')

            print(f"Stock Monitor - Update Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Number of Stocks: {len(stock_list)} | Interval: {interval}s")
            print("-" * 120)
            # 使用新函数格式化表头以实现正确对齐
            header_name = format_column_text('Name', 20, 'right')
            header_qty = format_column_text('Qty', 10, 'right')
            header_trend = format_column_text('Trend', 6, 'right')
            header_high = format_column_text('High', 8, 'right')
            header_low = format_column_text('Low', 8, 'right')
            header_price = format_column_text('Price', 10, 'right')
            header_change = format_column_text('Change%', 12, 'right')
            header_profit = format_column_text('Profit', 14, 'right')
            header_time = format_column_text('Time', 10, 'right')

            print(f"{header_name} {header_qty} {header_trend} {header_high} {header_low} {header_price} {header_change} {header_profit} {header_time}")
            print("-" * 120)

            global last_prices  # 使用全局变量存储价格

            # 并发获取所有股票数据
            all_stock_data = get_all_stock_data(stock_list)

            # 计算每只股票的收益并存储到列表中，用于排序
            stock_profits = []

            # 先收集所有股票的上次价格，用于趋势判断
            last_prices_for_display = {}
            for stock_item in stock_list:
                stock_code = stock_item['code']
                last_prices_for_display[stock_code] = last_prices.get(stock_code)

            # 然后处理股票数据并更新价格
            for stock_item in stock_list:
                stock_code = stock_item['code']
                stock_data = all_stock_data[stock_code]
                stock_info = stock_data['info']
                holding_quantity = stock_data['quantity']

                if stock_info:
                    # 获取上次价格用于趋势判断（使用循环开始时的值）
                    last_price = last_prices_for_display[stock_code]
                    # 计算利润金额但暂不显示
                    profit_amount = (stock_info['price'] - stock_info['pre_close']) * holding_quantity
                    # 更新最后价格
                    if stock_info['price'] > 0:  # 只有有效价格才更新
                        last_prices[stock_code] = stock_info['price']

                    # 添加到收益列表用于排序
                    stock_profits.append({
                        'stock_item': stock_item,
                        'stock_info': stock_info,
                        'holding_quantity': holding_quantity,
                        'profit_amount': profit_amount
                    })
                else:
                    # 如果无法获取数据，该股票的收益为0
                    stock_profits.append({
                        'stock_item': stock_item,
                        'stock_info': None,
                        'holding_quantity': holding_quantity,
                        'profit_amount': 0.0
                    })

            # 根据参数决定是否按收益金额排序
            if sort_by_profit:
                # 按收益金额排序（从高到低）
                stock_profits.sort(key=lambda x: x['profit_amount'], reverse=True)

            total_profit = 0.0
            total_cost = 0.0  # 总成本
            # 按排序后的顺序显示
            for stock_profit in stock_profits:
                stock_item = stock_profit['stock_item']
                stock_info = stock_profit['stock_info']
                holding_quantity = stock_profit['holding_quantity']

                if stock_info:
                    # 获取上次价格用于趋势判断（使用循环开始时的值）
                    last_price = last_prices_for_display[stock_item['code']]
                    # 显示股票信息并获取利润金额、当前价格和成本
                    profit_amount, current_price, cost = display_stock_info(stock_info, holding_quantity, last_price)
                    total_profit += profit_amount
                    total_cost += cost
                else:
                    name_display = stock_item['code'][:16]  # 限制名称长度为16个字符
                    # 使用新函数处理对齐以匹配正常显示
                    name_str = format_column_text(name_display, 20, 'right')
                    qty_str = format_column_text(holding_quantity, 10, 'right')
                    trend_str = format_with_color_padding('\033[93m-\033[0m', 6, '>')  # 趋势符号，右对齐
                    high_str = format_column_text('--', 8, 'right')  # 最高价
                    low_str = format_column_text('--', 8, 'right')   # 最低价
                    price_str = format_column_text('--', 10, 'right')
                    pct_str = format_column_text('--', 12, 'right')
                    profit_str = format_column_text('--', 14, 'right')  # 修正列宽
                    time_str = format_column_text('--', 10, 'right')
                    print(f"{name_str} {qty_str} {trend_str} {high_str} {low_str} {price_str} {pct_str} {profit_str} {time_str}")

            print("-" * 120)
            # 计算整体收益率
            overall_return_rate = 0.0
            if total_cost != 0:
                overall_return_rate = (total_profit / total_cost) * 100

            # 显示总收益和整体收益率
            if total_profit > 0:
                total_profit_str = f"\033[91m{total_profit:>10.2f}\033[0m"  # 红色表示总盈利
            elif total_profit < 0:
                total_profit_str = f"\033[92m{total_profit:>10.2f}\033[0m"  # 绿色表示总亏损
            else:
                total_profit_str = f"\033[93m{total_profit:>10.2f}\033[0m"  # 黄色表示无盈亏

            if overall_return_rate > 0:
                overall_return_rate_str = f"\033[91m{overall_return_rate:>8.2f}%\033[0m"  # 红色表示正收益率
            elif overall_return_rate < 0:
                overall_return_rate_str = f"\033[92m{overall_return_rate:>8.2f}%\033[0m"  # 绿色表示负收益率
            else:
                overall_return_rate_str = f"\033[93m{overall_return_rate:>8.2f}%\033[0m"  # 黄色表示零收益率

            # 使用新函数格式化标签以实现正确对齐
            total_profit_label = format_column_text('Total Profit:', 58, 'right')
            overall_return_label = format_column_text('Overall Return:', 15, 'right')
            print(f"{total_profit_label} {total_profit_str}  {overall_return_label} {overall_return_rate_str}")

            # 开始倒计时循环，只更新倒计时部分
            remaining_time = interval

            while remaining_time > 0:
                # 显示倒计时
                next_update_time = datetime.now() + timedelta(seconds=remaining_time)
                countdown_line = f"Next update: {next_update_time.strftime('%Y-%m-%d %H:%M:%S')} (Remaining: {remaining_time}s)"
                print(countdown_line)

                # 等待1秒
                time.sleep(1)
                remaining_time -= 1

                # 使用ANSI转义序列移动光标向上一行并更新内容
                if remaining_time > 0:
                    print(f"\033[A\033[2K\033[G", end="")

    except KeyboardInterrupt:
        print("\nMonitoring stopped")


if __name__ == "__main__":
    main()
