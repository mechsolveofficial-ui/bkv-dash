#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
BKV Portfolio Quarterly Optimizer (بهینه‌ساز فصلی پورتفوی بورس کالا)
=============================================================================
این اسکریپت از اولین تاریخ موجود در داده‌های بورس کالا شروع کرده و در دوره‌های
۳ ماهه (فصلی)، پورتفو را با گام‌های ۵٪ بهینه‌سازی می‌کند تا بیشترین سود تاریخی
در هر دوره ۳ ماهه حاصل شود.

خروجی:
۱. جدول خوانا در ترمینال
۲. فایل اکسل کامل و فرمت‌شده: portfolio_quarterly_report.xlsx
=============================================================================
"""

import os
import sys

# تنظیم انکودینگ ترمینال روی ویندوز برای نمایش صحیح متون فارسی و ایموجی‌ها
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import itertools
from datetime import datetime, timedelta
import jdatetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- تنظیمات ---
JSON_FILE_NAME = "bkv_data.json"
EXCEL_OUTPUT_NAME = "portfolio_quarterly_report.xlsx"
WEIGHT_STEP = 0.05  # گام ۵ درصد

COMMODITIES = [
    ('gold_995', 'طلای ۲۴ عیار', '#F59E0B'),
    ('gold_coin', 'سکه طلا', '#EAB308'),
    ('silver', 'نقره', '#94A3B8'),
    ('copper', 'مس', '#EA580C'),
    ('zinc', 'روی', '#64748B'),
    ('iron', 'سنگ آهن', '#991B1B'),
    ('bitumen', 'قیر', '#334155'),
]


def load_bkv_data():
    """بارگذاری فایل داده‌های بورس کالا."""
    # بررسی مسیر فعلی یا پوشه اسکریپت
    paths_to_check = [
        JSON_FILE_NAME,
        os.path.join(os.path.dirname(__file__), JSON_FILE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), JSON_FILE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', JSON_FILE_NAME),
        os.path.join('..', JSON_FILE_NAME),
    ]
    
    file_path = None
    for p in paths_to_check:
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        print(f"❌ خطا: فایل داده '{JSON_FILE_NAME}' یافت نشد.")
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"✅ فایل داده '{file_path}' با موفقیت بارگذاری شد.")
    return data


def parse_jdate(s):
    """تبدیل رشته تاریخ شمسی (YYYY/MM/DD) به شیء jdatetime.date."""
    y, m, d = map(int, s.split('/'))
    return jdatetime.date(y, m, d)


def add_jalali_months(jd, months=3):
    """اضافه کردن دقیق ۳ ماه به تاریخ شمسی با رعایت روزهای ماه."""
    total_months = (jd.month - 1) + months
    new_year = jd.year + total_months // 12
    new_month = total_months % 12 + 1
    # تعیین حداکثر روز در ماه جدید
    max_days = 29 if new_month == 12 else (30 if new_month > 6 else 31)
    new_day = min(jd.day, max_days)
    return jdatetime.date(new_year, new_month, new_day)


def generate_weight_combinations(num_assets, step=WEIGHT_STEP):
    """
    تولید تمام حالات ممکن تخصیص وزن با گام ۵٪ (مجموع وزن‌ها برابر ۱۰۰٪).
    معادل افراز عدد ۲۰ به num_assets بخش نامنفی.
    """
    if num_assets <= 0:
        return []
    if num_assets == 1:
        return [(1.0,)]

    total_units = int(round(1.0 / step))  # 20 واحد 0.05
    results = []

    def _recurse(remaining_units, current_weights):
        idx = len(current_weights)
        if idx == num_assets - 1:
            results.append(tuple(current_weights + [remaining_units * step]))
            return
        for u in range(remaining_units + 1):
            _recurse(remaining_units - u, current_weights + [u * step])

    _recurse(total_units, [])
    return results


def optimize_portfolio_for_period(returns_dict, step=WEIGHT_STEP):
    """
    یافتن بهترین ترکیب وزن‌ها با گام ۵٪ برای حداکثر کردن بازده دوره ۳ ماهه.
    """
    asset_keys = list(returns_dict.keys())
    if not asset_keys:
        return {}, 0.0

    if len(asset_keys) == 1:
        k = asset_keys[0]
        return {k: 1.0}, returns_dict[k]

    # تولید تمام ترکیبات با گام ۵٪
    combinations = generate_weight_combinations(len(asset_keys), step)
    
    best_weights = None
    best_return = -float('inf')

    # ارزیابی ترکیبات
    for w_tuple in combinations:
        ret = sum(w * returns_dict[k] for w, k in zip(w_tuple, asset_keys))
        if ret > best_return:
            best_return = ret
            best_weights = dict(zip(asset_keys, w_tuple))

    return best_weights, best_return


def run_optimization():
    raw_data = load_bkv_data()

    # ساخت ایندکس سریع تاریخ برای هر نماد
    comm_lookup = {}
    for cid, cname, _ in COMMODITIES:
        main_list = raw_data.get(cid, {}).get('main', [])
        comm_lookup[cid] = {row['date']: row for row in main_list}

    # استخراج تمام تاریخ‌های منحصربه‌فرد و مرتب‌سازی
    all_dates = set()
    for cid, cname, _ in COMMODITIES:
        all_dates.update(comm_lookup[cid].keys())
    
    sorted_dates = sorted(list(all_dates))
    j_dates = [parse_jdate(s) for s in sorted_dates]

    print(f"📊 بازه کلی داده‌ها: از {sorted_dates[0]} تا {sorted_dates[-1]} ({len(sorted_dates)} روز معاملاتی)")

    # بخش‌بندی به دوره‌های ۳ ماهه
    start_idx = 0
    periods = []
    while start_idx < len(j_dates) - 1:
        curr_jd = j_dates[start_idx]
        target_end_jd = add_jalali_months(curr_jd, 3)

        # پیدا کردن نزدیک‌ترین تاریخ روی یا قبل از تاریخ هدف
        valid_indices = [i for i, jd in enumerate(j_dates) if jd <= target_end_jd and i > start_idx]
        if not valid_indices:
            break
        end_idx = valid_indices[-1]

        periods.append((sorted_dates[start_idx], sorted_dates[end_idx]))
        start_idx = end_idx

    print(f"🗓️ تعداد دوره‌های ۳ ماهه شناسایی‌شده: {len(periods)} دوره")
    print("-" * 80)

    # اجرای بهینه‌سازی دوره به دوره
    cumulative_multiplier = 1.0
    period_results = []

    for p_idx, (s_date, e_date) in enumerate(periods, 1):
        s_jd = parse_jdate(s_date)
        e_jd = parse_jdate(e_date)
        cal_days = (e_jd.togregorian() - s_jd.togregorian()).days

        # بررسی در دسترس بودن داده‌ها برای هر نماد
        available_assets = {}
        for cid, cname, _ in COMMODITIES:
            has_start = s_date in comm_lookup[cid]
            has_end = e_date in comm_lookup[cid]
            if has_start and has_end:
                p_start = comm_lookup[cid][s_date]['ime_price']
                p_end = comm_lookup[cid][e_date]['ime_price']
                bubble_start = comm_lookup[cid][s_date]['bubble_pct']
                if p_start > 0 and p_end > 0:
                    ret = (p_end - p_start) / p_start
                    available_assets[cid] = {
                        'start_price': p_start,
                        'end_price': p_end,
                        'bubble_start': bubble_start,
                        'return': ret
                    }

        # بازده‌ها برای بهینه‌ساز
        returns_for_opt = {cid: info['return'] for cid, info in available_assets.items()}

        # اجرای بهینه‌سازی با گام ۵٪
        best_weights, period_return = optimize_portfolio_for_period(returns_for_opt, step=WEIGHT_STEP)

        # محاسبه بازده موثر مرکب کل سرمایه
        cumulative_multiplier *= (1.0 + period_return)
        effective_cumulative_return = (cumulative_multiplier - 1.0) * 100.0

        period_data = {
            'period_num': p_idx,
            'start_date': s_date,
            'end_date': e_date,
            'cal_days': cal_days,
            'available_assets': available_assets,
            'weights': best_weights,
            'period_return': period_return * 100.0,
            'cumulative_effective_return': effective_cumulative_return,
        }
        period_results.append(period_data)

    # چاپ خلاصه در کنسول
    print(f"{'دوره':<8}{'بازه زمانی':<25}{'نماد برتر':<15}{'سود دوره':>12}{'رشد موثر کل':>15}")
    print("=" * 80)
    for p in period_results:
        # نام نمادهای انتخاب‌شده با وزن غیر صفر
        chosen = [f"{dict((c[0], c[1]) for c in COMMODITIES)[cid]} ({w*100:.0f}%)" 
                  for cid, w in p['weights'].items() if w > 0]
        chosen_str = ", ".join(chosen) if chosen else "-"
        print(f"دوره {p['period_num']:02d}   {p['start_date']} -> {p['end_date']}   {chosen_str:<18} "
              f"{p['period_return']:>+10.2f}%   {p['cumulative_effective_return']:>+13.2f}%")
    print("=" * 80)

    # ایجاد فایل اکسل حرفه‌ای
    export_to_excel(period_results, EXCEL_OUTPUT_NAME)
    print(f"\n🎉 فایل اکسل گزارش با موفقیت ایجاد شد: {os.path.abspath(EXCEL_OUTPUT_NAME)}")


def export_to_excel(period_results, filename):
    """خروجی اکسل چند سطحی، راست‌به‌چپ و استایل‌بندی‌شده."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تحلیل پورتفوی سه ماهه"
    ws.views.sheetView[0].rightToLeft = True

    # فونت‌ها و رنگ‌ها
    font_header_main = Font(name='Tahoma', size=11, bold=True, color='FFFFFF')
    font_sub_header = Font(name='Tahoma', size=9, bold=True, color='E2E8F0')
    font_data = Font(name='Tahoma', size=9, color='0F172A')
    font_bold = Font(name='Tahoma', size=9, bold=True, color='0F172A')
    font_dash = Font(name='Tahoma', size=10, bold=True, color='94A3B8')
    font_profit = Font(name='Tahoma', size=9, bold=True, color='15803D')
    font_loss = Font(name='Tahoma', size=9, bold=True, color='B91C1C')

    fill_period_header = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
    fill_sub_header = PatternFill(start_color='334155', end_color='334155', fill_type='solid')
    fill_summary_header = PatternFill(start_color='047857', end_color='047857', fill_type='solid')
    fill_summary_sub = PatternFill(start_color='065F46', end_color='065F46', fill_type='solid')
    fill_zebra = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')

    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_left = Alignment(horizontal='left', vertical='center')
    align_right = Alignment(horizontal='right', vertical='center')

    thin_border_side = Side(border_style='thin', color='CBD5E1')
    thick_border_left = Side(border_style='medium', color='64748B')
    border_cell = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    border_col_end = Border(left=thick_border_left, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    # سطر ۱ و ۲: هدرها
    # ستون‌های دوره
    ws.merge_cells('A1:D1')
    ws['A1'] = "مشخصات دوره زمانی"
    ws['A1'].font = font_header_main
    ws['A1'].fill = fill_period_header
    ws['A1'].alignment = align_center

    sub_headers_meta = ["شماره دوره", "از تاریخ", "تا تاریخ", "طول دوره (روز)"]
    for col_idx, sh in enumerate(sub_headers_meta, 1):
        cell = ws.cell(row=2, column=col_idx, value=sh)
        cell.font = font_sub_header
        cell.fill = fill_sub_header
        cell.alignment = align_center
        cell.border = border_cell

    col_cursor = 5
    # ستون‌های هر نماد (۴ ستون برای هر نماد)
    comm_colors = {
        'gold_995': 'B45309',
        'gold_coin': 'A16207',
        'silver': '475569',
        'copper': 'C2410C',
        'zinc': '475569',
        'iron': '991B1B',
        'bitumen': '1E293B'
    }

    comm_start_cols = {}
    for cid, cname, _ in COMMODITIES:
        start_c = col_cursor
        end_c = col_cursor + 3
        comm_start_cols[cid] = start_c

        ws.merge_cells(start_row=1, start_column=start_c, end_row=1, end_column=end_c)
        header_cell = ws.cell(row=1, column=start_c, value=f"{cname}")
        header_cell.font = font_header_main
        header_cell.fill = PatternFill(start_color=comm_colors.get(cid, '334155'), fill_type='solid')
        header_cell.alignment = align_center

        sub_titles = [
            "وزن در پورتفو",
            "تغییر قیمت ۳ ماهه",
            "حباب اول دوره",
            "قیمت خرید (ریال)"
        ]
        for offset, st in enumerate(sub_titles):
            sc = ws.cell(row=2, column=start_c + offset, value=st)
            sc.font = font_sub_header
            sc.fill = fill_sub_header
            sc.alignment = align_center
            sc.border = border_cell if offset < 3 else border_col_end

        col_cursor += 4

    # ستون‌های جمع‌بندی عملکرد پورتفو در انتهای جدول
    summary_start_col = col_cursor
    ws.merge_cells(start_row=1, start_column=summary_start_col, end_row=1, end_column=summary_start_col + 1)
    sum_header = ws.cell(row=1, column=summary_start_col, value="عملکرد پورتفوی بهینه‌شده")
    sum_header.font = font_header_main
    sum_header.fill = fill_summary_header
    sum_header.alignment = align_center

    sc1 = ws.cell(row=2, column=summary_start_col, value="سود دوره ۳ ماهه (٪)")
    sc1.font = font_sub_header
    sc1.fill = fill_summary_sub
    sc1.alignment = align_center
    sc1.border = border_cell

    sc2 = ws.cell(row=2, column=summary_start_col + 1, value="رشد موثر سرمایه از ابتدا (٪)")
    sc2.font = font_sub_header
    sc2.fill = fill_summary_sub
    sc2.alignment = align_center
    sc2.border = border_cell

    # نوشتن سطرهای داده
    current_row = 3
    for p_idx, p in enumerate(period_results, 1):
        is_even = (p_idx % 2 == 0)
        row_fill = fill_zebra if is_even else None

        # اطلاعات دوره
        c_p = ws.cell(row=current_row, column=1, value=f"دوره {p['period_num']:02d}")
        c_s = ws.cell(row=current_row, column=2, value=p['start_date'])
        c_e = ws.cell(row=current_row, column=3, value=p['end_date'])
        c_d = ws.cell(row=current_row, column=4, value=p['cal_days'])

        for c in (c_p, c_s, c_e, c_d):
            c.font = font_bold if c == c_p else font_data
            c.alignment = align_center
            c.border = border_cell
            if row_fill:
                c.fill = row_fill

        # اطلاعات هر نماد
        for cid, cname, _ in COMMODITIES:
            start_col = comm_start_cols[cid]
            is_avail = cid in p['available_assets']

            cell_weight = ws.cell(row=current_row, column=start_col)
            cell_ret = ws.cell(row=current_row, column=start_col + 1)
            cell_bubble = ws.cell(row=current_row, column=start_col + 2)
            cell_price = ws.cell(row=current_row, column=start_col + 3)

            if is_avail:
                info = p['available_assets'][cid]
                w = p['weights'].get(cid, 0.0)

                # ۱. درصد انتخابی از پورتفو
                cell_weight.value = w
                cell_weight.number_format = '0.0%'
                cell_weight.font = font_bold if w > 0 else font_data
                cell_weight.alignment = align_center

                # رنگ متمایز برای نمادی که در پورتفو انتخاب شده
                if w > 0:
                    cell_weight.fill = PatternFill(start_color='DCFCE7', end_color='DCFCE7', fill_type='solid')

                # ۲. درصد تغییر قیمت نماد
                ret_val = info['return']
                cell_ret.value = ret_val
                cell_ret.number_format = '+0.00%;-0.00%;0.00%'
                cell_ret.font = font_profit if ret_val > 0 else (font_loss if ret_val < 0 else font_data)
                cell_ret.alignment = align_center

                # ۳. حباب قیمتی در اول دوره
                bubble_val = info['bubble_start'] / 100.0
                cell_bubble.value = bubble_val
                cell_bubble.number_format = '+0.00%;-0.00%;0.00%'
                cell_bubble.font = font_loss if bubble_val > 0 else (font_profit if bubble_val < 0 else font_data)
                cell_bubble.alignment = align_center

                # ۴. قیمت خرید در اول دوره
                cell_price.value = info['start_price']
                cell_price.number_format = '#,##0'
                cell_price.font = font_data
                cell_price.alignment = align_right

            else:
                # نماد در این دوره هنوز تاریخچه قیمتی ندارد
                for cell in (cell_weight, cell_ret, cell_bubble, cell_price):
                    cell.value = "-"
                    cell.font = font_dash
                    cell.alignment = align_center

            for idx, c in enumerate((cell_weight, cell_ret, cell_bubble, cell_price)):
                c.border = border_cell if idx < 3 else border_col_end
                if row_fill and c.fill.fill_type is None:
                    c.fill = row_fill

        # عملکرد پورتفو (ستون‌های نهایی)
        c_pret = ws.cell(row=current_row, column=summary_start_col, value=p['period_return'] / 100.0)
        c_pret.number_format = '+0.00%;-0.00%;0.00%'
        c_pret.font = font_profit if p['period_return'] > 0 else (font_loss if p['period_return'] < 0 else font_data)
        c_pret.alignment = align_center
        c_pret.border = border_cell
        if row_fill:
            c_pret.fill = row_fill

        c_cum = ws.cell(row=current_row, column=summary_start_col + 1, value=p['cumulative_effective_return'] / 100.0)
        c_cum.number_format = '+0.00%;-0.00%;0.00%'
        c_cum.font = font_bold
        c_cum.alignment = align_center
        c_cum.border = border_cell
        # هایلایت ملایم سبز برای ستون رشد موثر کل
        c_cum.fill = PatternFill(start_color='E0F2FE', end_color='E0F2FE', fill_type='solid')

        current_row += 1

    # تنظیم عرض ستون‌ها برای خوانایی بهینه
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.number_format and ('%' in cell.number_format or '#' in cell.number_format):
                max_len = max(max_len, 12)
            else:
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 13)

    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 24
    for r in range(3, current_row):
        ws.row_dimensions[r].height = 20

    wb.save(filename)


if __name__ == "__main__":
    run_optimization()
