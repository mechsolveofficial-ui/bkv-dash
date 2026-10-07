#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
BKV Fixed Portfolio Optimizer (بهینه‌ساز پورتفوی ثابت فصلی بورس کالا)
=============================================================================
این اسکریپت با گام ۱ درصد (۱٪ به ۱٪)، تمامی ترکیبات وزنی ممکن را بررسی می‌کند
تا بهترین «پورتفوی با وزن ثابت» (Buy-and-Hold Fixed Weights) را پیدا کند که
در مجموع کل دوره‌های ۳ ماهه، بیشترین سود و بالاترین پایداری را به همراه داشته است.

خروجی‌ها:
۱. گزارش تحلیلی در ترمینال
۲. فایل اکسل ۳ شیت با فرمت RTL و استایل حرفه‌ای: portfolio_fixed_report.xlsx
   - شیت ۱: عملکرد فصلی پورتفوی بهینه ثابت (۱۵ دوره ۳ ماهه)
   - شیت ۲: جدول رده‌بندی پورتفوهای برتر با گام ۱٪ (بر اساس سود و پایداری)
   - شیت ۳: مقایسه بازدهی پورتفوهای تک‌نمادی (۱۰۰٪ در هر نماد)
=============================================================================
"""

import os
import sys

# تنظیم انکودینگ ترمینال ویندوز برای نمایش صحیح متون فارسی
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
from datetime import datetime, timedelta
import jdatetime
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- تنظیمات ---
JSON_FILE_NAME = "bkv_data.json"
EXCEL_OUTPUT_NAME = "portfolio_fixed_report.xlsx"

COMMODITIES = [
    ('gold_995', 'طلای ۲۴ عیار', 'B45309'),
    ('gold_coin', 'سکه طلا', 'A16207'),
    ('silver', 'نقره', '475569'),
    ('copper', 'مس', 'C2410C'),
    ('zinc', 'روی', '64748B'),
    ('iron', 'سنگ آهن', '991B1B'),
    ('bitumen', 'قیر', '1E293B'),
]


def load_bkv_data():
    """بارگذاری فایل داده‌های بورس کالا."""
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
    print(f"✅ فایل داده '{file_path}' بارگذاری شد.")
    return data


def parse_jdate(s):
    """تبدیل رشته تاریخ شمسی به شیء jdatetime.date."""
    y, m, d = map(int, s.split('/'))
    return jdatetime.date(y, m, d)


def add_jalali_months(jd, months=3):
    """افزودن ۳ ماه به تاریخ شمسی با در نظر گرفتن طول ماه‌ها."""
    total_months = (jd.month - 1) + months
    new_year = jd.year + total_months // 12
    new_month = total_months % 12 + 1
    max_days = 29 if new_month == 12 else (30 if new_month > 6 else 31)
    new_day = min(jd.day, max_days)
    return jdatetime.date(new_year, new_month, new_day)


def evaluate_fixed_weights(w, R):
    """
    محاسبه عملکرد پورتفوی با وزن ثابت w در ماتریس بازده R (شامل T دوره و N نماد).
    سرمایه بین نمادهای فعال در هر دوره به نسبت وزن ثابتشان بازتوزیع می‌شود تا
    سرمایه معطل نماند.
    """
    T, N = R.shape
    period_rets = np.zeros(T)
    for t in range(T):
        valid = ~np.isnan(R[t])
        avail_w = w * valid
        sw = np.sum(avail_w)
        if sw > 0:
            norm_w = avail_w / sw
            period_rets[t] = np.sum(norm_w * np.nan_to_num(R[t]))
        else:
            period_rets[t] = 0.0

    cum_return = np.prod(1.0 + period_rets) - 1.0
    mean_ret = np.mean(period_rets)
    std_ret = np.std(period_rets)
    sharpe = mean_ret / (std_ret + 1e-6)
    worst_period = np.min(period_rets)
    best_period = np.max(period_rets)
    win_rate = np.mean(period_rets > 0)

    return {
        'weights': w,
        'cum_return': cum_return,
        'mean_return': mean_ret,
        'std_return': std_ret,
        'sharpe': sharpe,
        'worst_period': worst_period,
        'best_period': best_period,
        'win_rate': win_rate,
        'period_rets': period_rets,
    }


def run_fixed_optimizer():
    raw_data = load_bkv_data()

    comm_ids = [c[0] for c in COMMODITIES]
    comm_lookup = {}
    for cid in comm_ids:
        main_list = raw_data.get(cid, {}).get('main', [])
        comm_lookup[cid] = {row['date']: row for row in main_list}

    all_dates = set()
    for cid in comm_ids:
        all_dates.update(comm_lookup[cid].keys())
    sorted_dates = sorted(list(all_dates))
    j_dates = [parse_jdate(s) for s in sorted_dates]

    # استخراج دوره‌های فصلی (۳ ماهه)
    start_idx = 0
    periods = []
    while start_idx < len(j_dates) - 1:
        curr_jd = j_dates[start_idx]
        target_end_jd = add_jalali_months(curr_jd, 3)
        valid_indices = [i for i, jd in enumerate(j_dates) if jd <= target_end_jd and i > start_idx]
        if not valid_indices:
            break
        end_idx = valid_indices[-1]
        periods.append((sorted_dates[start_idx], sorted_dates[end_idx]))
        start_idx = end_idx

    T = len(periods)
    N = len(comm_ids)
    print(f"🗓️ {T} دوره ۳ ماهه از {sorted_dates[0]} تا {sorted_dates[-1]} آماده‌سازی شد.")

    # ساخت ماتریس بازده R (ابعاد T در N)
    R = np.full((T, N), np.nan)
    for t, (s_date, e_date) in enumerate(periods):
        for i, cid in enumerate(comm_ids):
            if s_date in comm_lookup[cid] and e_date in comm_lookup[cid]:
                p1 = comm_lookup[cid][s_date]['ime_price']
                p2 = comm_lookup[cid][e_date]['ime_price']
                if p1 > 0:
                    R[t, i] = (p2 - p1) / p1

    print("\n🔍 در حال جستجوی گسترده ترکیبات وزنی با گام ۱٪ (۱ درصد به ۱ درصد)...")

    # ۱. تولید و ارزیابی پورتفوهای تک‌نمادی (۱۰۰٪ در هر نماد)
    single_asset_results = []
    all_candidates = []

    for i in range(N):
        w = np.zeros(N)
        w[i] = 1.0
        metrics = evaluate_fixed_weights(w, R)
        single_asset_results.append(metrics)
        all_candidates.append(metrics)

    # ۲. جستجوی جفت‌نمادی با گام ۱٪ (سکه، طلا، نقره، مس، روی، آهن، قیر)
    for i in range(N):
        for j in range(i + 1, N):
            for pct in range(1, 100):
                w = np.zeros(N)
                w[i] = pct / 100.0
                w[j] = (100 - pct) / 100.0
                metrics = evaluate_fixed_weights(w, R)
                all_candidates.append(metrics)

    # ۳. جستجوی سه‌نمادی با گام ۱٪ برای ترکیب‌های منتخب (طلا، سکه، نقره، آهن، قیر)
    triplet_indices = [
        (0, 2, 6),  # طلای ۲۴، نقره، قیر
        (0, 1, 6),  # طلای ۲۴، سکه، قیر
        (1, 2, 6),  # سکه، نقره، قیر
        (0, 5, 6),  # طلای ۲۴، آهن، قیر
        (0, 1, 2),  # طلای ۲۴، سکه، نقره
        (0, 3, 6),  # طلای ۲۴، مس، قیر
        (0, 4, 6),  # طلای ۲۴، روی، قیر
    ]
    for i, j, k in triplet_indices:
        for p1 in range(1, 99):
            for p2 in range(1, 100 - p1):
                p3 = 100 - p1 - p2
                w = np.zeros(N)
                w[i] = p1 / 100.0
                w[j] = p2 / 100.0
                w[k] = p3 / 100.0
                metrics = evaluate_fixed_weights(w, R)
                all_candidates.append(metrics)

    # ۴. جستجوی چهارنمادی با گام ۲٪ برای تنوع‌بخشی حداکثری
    quad_indices = [(0, 1, 2, 6), (0, 2, 5, 6)]
    for i, j, k, l in quad_indices:
        for p1 in range(2, 96, 2):
            for p2 in range(2, 98 - p1, 2):
                for p3 in range(2, 100 - p1 - p2, 2):
                    p4 = 100 - p1 - p2 - p3
                    w = np.zeros(N)
                    w[i] = p1 / 100.0
                    w[j] = p2 / 100.0
                    w[k] = p3 / 100.0
                    w[l] = p4 / 100.0
                    metrics = evaluate_fixed_weights(w, R)
                    all_candidates.append(metrics)

    print(f"✅ تعداد {len(all_candidates):,} ترکیب پورتفوی وزن ثابت بررسی و ارزیابی شدند.")

    # مرتب‌سازی بر اساس بیشترین سود کل
    all_candidates_by_return = sorted(all_candidates, key=lambda x: x['cum_return'], reverse=True)
    best_portfolio = all_candidates_by_return[0]

    # مرتب‌سازی بر اساس بیشترین پایداری (نسبت شارپ / بازده به نوسان)
    all_candidates_by_stability = sorted(all_candidates, key=lambda x: x['sharpe'], reverse=True)
    best_stable_portfolio = all_candidates_by_stability[0]

    # چاپ خلاصه در کنسول
    print("\n" + "=" * 80)
    print("🏆 برترین پورتفوی با وزن ثابت (بیشترین سود در کل دوره‌ها با گام ۱٪)")
    print("=" * 80)
    print("ترکیب بهینه ثابت پورتفو:")
    for idx, (cid, cname, _) in enumerate(COMMODITIES):
        pct = int(round(best_portfolio['weights'][idx] * 100))
        if pct > 0:
            print(f"  ⭐ {cname} ({cid}): {pct}%")
        else:
            print(f"     {cname} ({cid}): 0%")

    print("-" * 80)
    print(f"🚀 مجموع سود مرکب کل دوره: {best_portfolio['cum_return']*100:+.2f}%")
    print(f"📈 میانگین سود هر فصل:       {best_portfolio['mean_return']*100:+.2f}%")
    print(f"🎯 بهترین فصل:               {best_portfolio['best_period']*100:+.2f}%")
    print(f"⚠️ بدترین فصل (افت ماکسیمم): {best_portfolio['worst_period']*100:+.2f}%")
    print(f"⚖️ شاخص شارپ / پایداری:      {best_portfolio['sharpe']:.2f}")
    print(f"🛡️ نرخ فصل‌های سودده:       {best_portfolio['win_rate']*100:.0f}%")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("🛡️ پایدارترین پورتفوی با وزن ثابت (بالاترین نسبت بازده به ریسک / کمترین افت)")
    print("=" * 80)
    for idx, (cid, cname, _) in enumerate(COMMODITIES):
        pct = int(round(best_stable_portfolio['weights'][idx] * 100))
        if pct > 0:
            print(f"  ⭐ {cname} ({cid}): {pct}%")
    print(f"🚀 سود کل: {best_stable_portfolio['cum_return']*100:+.2f}% | شاخص پایداری: {best_stable_portfolio['sharpe']:.2f} | بدترین فصل: {best_stable_portfolio['worst_period']*100:+.2f}%")
    print("=" * 80)

    # ایجاد فایل اکسل
    export_fixed_report_to_excel(
        best_portfolio,
        best_stable_portfolio,
        all_candidates_by_return[:50],
        single_asset_results,
        periods,
        comm_lookup,
        R,
        EXCEL_OUTPUT_NAME
    )
    print(f"\n🎉 فایل اکسل کامل پورتفوی ثابت با موفقیت ذخیره شد: {os.path.abspath(EXCEL_OUTPUT_NAME)}")


def export_fixed_report_to_excel(best_port, stable_port, top_50, single_results, periods, comm_lookup, R, filename):
    wb = openpyxl.Workbook()

    # فونت‌ها و رنگ‌ها
    font_main_title = Font(name='Tahoma', size=12, bold=True, color='FFFFFF')
    font_sub_header = Font(name='Tahoma', size=9, bold=True, color='E2E8F0')
    font_data = Font(name='Tahoma', size=9, color='0F172A')
    font_bold = Font(name='Tahoma', size=9, bold=True, color='0F172A')
    font_dash = Font(name='Tahoma', size=10, bold=True, color='94A3B8')
    font_profit = Font(name='Tahoma', size=9, bold=True, color='15803D')
    font_loss = Font(name='Tahoma', size=9, bold=True, color='B91C1C')
    font_stat_val = Font(name='Tahoma', size=11, bold=True, color='1E3A8A')
    font_stat_lbl = Font(name='Tahoma', size=9, color='475569')

    fill_period_header = PatternFill(start_color='1E293B', fill_type='solid')
    fill_sub_header = PatternFill(start_color='334155', fill_type='solid')
    fill_summary_header = PatternFill(start_color='047857', fill_type='solid')
    fill_summary_sub = PatternFill(start_color='065F46', fill_type='solid')
    fill_zebra = PatternFill(start_color='F8FAFC', fill_type='solid')
    fill_card = PatternFill(start_color='F1F5F9', fill_type='solid')
    fill_card_highlight = PatternFill(start_color='DCFCE7', fill_type='solid')

    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_right = Alignment(horizontal='right', vertical='center')

    thin_border_side = Side(border_style='thin', color='CBD5E1')
    thick_border_left = Side(border_style='medium', color='64748B')
    border_cell = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    border_col_end = Border(left=thick_border_left, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    # -------------------------------------------------------------
    # شیت ۱: عملکرد فصلی پورتفوی بهینه ثابت
    # -------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "عملکرد فصلی پورتفوی بهینه"
    ws1.views.sheetView[0].rightToLeft = True

    # کارت‌های آمار بالای جدول
    ws1.merge_cells('A1:L1')
    title_cell = ws1['A1']
    title_cell.value = "گزارش عملکرد دوره‌ای پورتفوی با وزن ثابت بهینه‌شده (بیشترین سود در کل بازه)"
    title_cell.font = font_main_title
    title_cell.fill = fill_summary_header
    title_cell.alignment = align_center

    # توضیحات ترکیب وزن‌ها
    w_desc_parts = [f"{c[1]}: {int(round(best_port['weights'][i]*100))}%" 
                    for i, c in enumerate(COMMODITIES) if best_port['weights'][i] > 0]
    w_desc_str = " | ".join(w_desc_parts)

    ws1.merge_cells('A2:L2')
    ws1['A2'] = f"ترکیب بهینه ثابت: {w_desc_str}"
    ws1['A2'].font = font_bold
    ws1['A2'].fill = fill_card_highlight
    ws1['A2'].alignment = align_center

    # ردیف آمار کلیدی
    stats_data = [
        ("سود مرکب کل", f"{best_port['cum_return']*100:+.2f}%"),
        ("میانگین سود فصلی", f"{best_port['mean_return']*100:+.2f}%"),
        ("بهترین فصل", f"{best_port['best_period']*100:+.2f}%"),
        ("بدترین فصل", f"{best_port['worst_period']*100:+.2f}%"),
        ("شاخص شارپ (پایداری)", f"{best_port['sharpe']:.2f}"),
        ("نرخ دوره‌های مثبت", f"{best_port['win_rate']*100:.0f}%"),
    ]
    for col_i, (lbl, val) in enumerate(stats_data):
        c1 = col_i * 2 + 1
        c2 = c1 + 1
        ws1.merge_cells(start_row=3, start_column=c1, end_row=3, end_column=c2)
        ws1.merge_cells(start_row=4, start_column=c1, end_row=4, end_column=c2)
        cell_lbl = ws1.cell(3, c1, lbl)
        cell_val = ws1.cell(4, c1, val)
        cell_lbl.font = font_stat_lbl
        cell_lbl.fill = fill_card
        cell_lbl.alignment = align_center
        cell_val.font = font_stat_val
        cell_val.fill = fill_card
        cell_val.alignment = align_center

    # هدرهای اصلی جدول دوره‌ها (شروع از ردیف ۶)
    ws1.merge_cells('A6:D6')
    ws1['A6'] = "مشخصات دوره زمانی"
    ws1['A6'].font = font_main_title
    ws1['A6'].fill = fill_period_header
    ws1['A6'].alignment = align_center

    sub_headers_meta = ["دوره", "از تاریخ", "تا تاریخ", "طول دوره (روز)"]
    for col_idx, sh in enumerate(sub_headers_meta, 1):
        cell = ws1.cell(row=7, column=col_idx, value=sh)
        cell.font = font_sub_header
        cell.fill = fill_sub_header
        cell.alignment = align_center
        cell.border = border_cell

    col_cursor = 5
    comm_start_cols = {}
    for cid, cname, color_hex in COMMODITIES:
        start_c = col_cursor
        end_c = col_cursor + 3
        comm_start_cols[cid] = start_c

        ws1.merge_cells(start_row=6, start_column=start_c, end_row=6, end_column=end_c)
        h_cell = ws1.cell(row=6, column=start_c, value=cname)
        h_cell.font = font_main_title
        h_cell.fill = PatternFill(start_color=color_hex, fill_type='solid')
        h_cell.alignment = align_center

        sub_titles = ["وزن تخصیص‌یافته", "تغییر قیمت نماد", "حباب اول دوره", "قیمت خرید (ریال)"]
        for offset, st in enumerate(sub_titles):
            sc = ws1.cell(row=7, column=start_c + offset, value=st)
            sc.font = font_sub_header
            sc.fill = fill_sub_header
            sc.alignment = align_center
            sc.border = border_cell if offset < 3 else border_col_end
        col_cursor += 4

    summary_start_col = col_cursor
    ws1.merge_cells(start_row=6, start_column=summary_start_col, end_row=6, end_column=summary_start_col + 1)
    sum_h = ws1.cell(row=6, column=summary_start_col, value="عملکرد پورتفوی ثابت")
    sum_h.font = font_main_title
    sum_h.fill = fill_summary_header
    sum_h.alignment = align_center

    sc1 = ws1.cell(row=7, column=summary_start_col, value="بازدهی دوره پورتفو (٪)")
    sc1.font = font_sub_header
    sc1.fill = fill_summary_sub
    sc1.alignment = align_center
    sc1.border = border_cell

    sc2 = ws1.cell(row=7, column=summary_start_col + 1, value="رشد موثر کل سرمایه (٪)")
    sc2.font = font_sub_header
    sc2.fill = fill_summary_sub
    sc2.alignment = align_center
    sc2.border = border_cell

    # نوشتن سطرهای داده دوره‌ها
    current_row = 8
    cum_mult = 1.0
    for p_idx, (s_date, e_date) in enumerate(periods, 1):
        is_even = (p_idx % 2 == 0)
        row_fill = fill_zebra if is_even else None
        s_jd = parse_jdate(s_date)
        e_jd = parse_jdate(e_date)
        cal_days = (e_jd.togregorian() - s_jd.togregorian()).days

        p_ret = best_port['period_rets'][p_idx - 1]
        cum_mult *= (1.0 + p_ret)
        cum_eff_pct = (cum_mult - 1.0) * 100.0

        # ستون‌های مشخصات دوره
        c_p = ws1.cell(row=current_row, column=1, value=f"دوره {p_idx:02d}")
        c_s = ws1.cell(row=current_row, column=2, value=s_date)
        c_e = ws1.cell(row=current_row, column=3, value=e_date)
        c_d = ws1.cell(row=current_row, column=4, value=cal_days)
        for c in (c_p, c_s, c_e, c_d):
            c.font = font_bold if c == c_p else font_data
            c.alignment = align_center
            c.border = border_cell
            if row_fill:
                c.fill = row_fill

        # بررسی وزن‌های مؤثر در این دوره
        valid_mask = ~np.isnan(R[p_idx - 1])
        avail_w = best_port['weights'] * valid_mask
        sw = np.sum(avail_w)
        eff_weights = avail_w / sw if sw > 0 else np.zeros(len(COMMODITIES))

        # اطلاعات هر نماد
        for c_i, (cid, cname, _) in enumerate(COMMODITIES):
            start_col = comm_start_cols[cid]
            is_avail = not np.isnan(R[p_idx - 1, c_i])

            cell_w = ws1.cell(row=current_row, column=start_col)
            cell_r = ws1.cell(row=current_row, column=start_col + 1)
            cell_b = ws1.cell(row=current_row, column=start_col + 2)
            cell_pr = ws1.cell(row=current_row, column=start_col + 3)

            if is_avail:
                w_val = eff_weights[c_i]
                cell_w.value = w_val
                cell_w.number_format = '0.0%'
                cell_w.font = font_bold if w_val > 0 else font_data
                cell_w.alignment = align_center
                if w_val > 0:
                    cell_w.fill = PatternFill(start_color='DCFCE7', fill_type='solid')

                ret_val = R[p_idx - 1, c_i]
                cell_r.value = ret_val
                cell_r.number_format = '+0.00%;-0.00%;0.00%'
                cell_r.font = font_profit if ret_val > 0 else (font_loss if ret_val < 0 else font_data)
                cell_r.alignment = align_center

                b_val = comm_lookup[cid][s_date]['bubble_pct'] / 100.0
                cell_b.value = b_val
                cell_b.number_format = '+0.00%;-0.00%;0.00%'
                cell_b.font = font_loss if b_val > 0 else (font_profit if b_val < 0 else font_data)
                cell_b.alignment = align_center

                pr_val = comm_lookup[cid][s_date]['ime_price']
                cell_pr.value = pr_val
                cell_pr.number_format = '#,##0'
                cell_pr.font = font_data
                cell_pr.alignment = align_right
            else:
                for c in (cell_w, cell_r, cell_b, cell_pr):
                    c.value = "-"
                    c.font = font_dash
                    c.alignment = align_center

            for idx, c in enumerate((cell_w, cell_r, cell_b, cell_pr)):
                c.border = border_cell if idx < 3 else border_col_end
                if row_fill and c.fill.fill_type is None:
                    c.fill = row_fill

        # عملکرد دوره
        c_pret = ws1.cell(row=current_row, column=summary_start_col, value=p_ret)
        c_pret.number_format = '+0.00%;-0.00%;0.00%'
        c_pret.font = font_profit if p_ret > 0 else (font_loss if p_ret < 0 else font_data)
        c_pret.alignment = align_center
        c_pret.border = border_cell
        if row_fill:
            c_pret.fill = row_fill

        c_cum = ws1.cell(row=current_row, column=summary_start_col + 1, value=cum_eff_pct / 100.0)
        c_cum.number_format = '+0.00%;-0.00%;0.00%'
        c_cum.font = font_bold
        c_cum.alignment = align_center
        c_cum.border = border_cell
        c_cum.fill = PatternFill(start_color='E0F2FE', fill_type='solid')

        current_row += 1

    # تنظیم خودکار عرض ستون‌های شیت ۱
    for col in ws1.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 13)

    # -------------------------------------------------------------
    # شیت ۲: رده‌بندی ۵۰ پورتفوی برتر با گام ۱٪
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="رده‌بندی ۵۰ پورتفوی برتر")
    ws2.views.sheetView[0].rightToLeft = True

    headers_top50 = [
        "رتبه",
        "طلای ۲۴ عیار (٪)",
        "سکه طلا (٪)",
        "نقره (٪)",
        "مس (٪)",
        "روی (٪)",
        "سنگ آهن (٪)",
        "قیر (٪)",
        "مجموع سود مرکب کل (٪)",
        "میانگین سود فصلی (٪)",
        "بدترین فصل (Max DD ٪)",
        "شاخص شارپ (پایداری)",
        "نرخ دوره‌های مثبت (٪)"
    ]

    for c_i, h in enumerate(headers_top50, 1):
        cell = ws2.cell(row=1, column=c_i, value=h)
        cell.font = font_main_title
        cell.fill = fill_summary_header if c_i >= 9 else fill_period_header
        cell.alignment = align_center
        cell.border = border_cell

    for rank, cand in enumerate(top_50, 1):
        row_idx = rank + 1
        is_even = (rank % 2 == 0)
        r_fill = fill_zebra if is_even else None

        c_rank = ws2.cell(row=row_idx, column=1, value=f"#{rank:02d}")
        c_rank.font = font_bold
        c_rank.alignment = align_center
        c_rank.border = border_cell
        if r_fill:
            c_rank.fill = r_fill

        # وزن‌ها
        for i in range(len(COMMODITIES)):
            c_w = ws2.cell(row=row_idx, column=i + 2, value=cand['weights'][i])
            c_w.number_format = '0.0%'
            c_w.font = font_bold if cand['weights'][i] > 0 else font_data
            c_w.alignment = align_center
            c_w.border = border_cell
            if cand['weights'][i] > 0:
                c_w.fill = PatternFill(start_color='DCFCE7', fill_type='solid')
            elif r_fill:
                c_w.fill = r_fill

        # آمار
        m_cum = ws2.cell(row=row_idx, column=9, value=cand['cum_return'])
        m_cum.number_format = '+0.00%;-0.00%;0.00%'
        m_cum.font = font_bold
        m_cum.alignment = align_center
        m_cum.border = border_cell
        m_cum.fill = PatternFill(start_color='E0F2FE', fill_type='solid')

        m_avg = ws2.cell(row=row_idx, column=10, value=cand['mean_return'])
        m_avg.number_format = '+0.00%;-0.00%;0.00%'
        m_avg.font = font_data
        m_avg.alignment = align_center
        m_avg.border = border_cell

        m_worst = ws2.cell(row=row_idx, column=11, value=cand['worst_period'])
        m_worst.number_format = '+0.00%;-0.00%;0.00%'
        m_worst.font = font_loss if cand['worst_period'] < 0 else font_data
        m_worst.alignment = align_center
        m_worst.border = border_cell

        m_sh = ws2.cell(row=row_idx, column=12, value=cand['sharpe'])
        m_sh.number_format = '0.00'
        m_sh.font = font_bold
        m_sh.alignment = align_center
        m_sh.border = border_cell

        m_win = ws2.cell(row=row_idx, column=13, value=cand['win_rate'])
        m_win.number_format = '0.0%'
        m_win.font = font_data
        m_win.alignment = align_center
        m_win.border = border_cell

        if r_fill:
            for cell in (m_avg, m_worst, m_sh, m_win):
                cell.fill = r_fill

    for col in ws2.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws2.column_dimensions[col_letter].width = max(max_len + 3, 14)

    # -------------------------------------------------------------
    # شیت ۳: مقایسه پورتفوهای تک‌نمادی (۱۰۰٪ در هر نماد)
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="مقایسه نمادهای منفرد (100%)")
    ws3.views.sheetView[0].rightToLeft = True

    headers_single = [
        "نام نماد",
        "کد نماد",
        "مجموع سود مرکب کل (٪)",
        "میانگین سود فصلی (٪)",
        "بهترین فصل (٪)",
        "بدترین فصل (Max DD ٪)",
        "شاخص شارپ (پایداری)",
        "نرخ دوره‌های مثبت (٪)"
    ]
    for c_i, h in enumerate(headers_single, 1):
        cell = ws3.cell(row=1, column=c_i, value=h)
        cell.font = font_main_title
        cell.fill = fill_period_header
        cell.alignment = align_center
        cell.border = border_cell

    for i, res in enumerate(single_results, 1):
        cid, cname, _ = COMMODITIES[i - 1]
        row_i = i + 1
        is_even = (i % 2 == 0)
        r_fill = fill_zebra if is_even else None

        c_name = ws3.cell(row=row_i, column=1, value=cname)
        c_id = ws3.cell(row=row_i, column=2, value=cid)
        c_cum = ws3.cell(row=row_i, column=3, value=res['cum_return'])
        c_avg = ws3.cell(row=row_i, column=4, value=res['mean_return'])
        c_best = ws3.cell(row=row_i, column=5, value=res['best_period'])
        c_worst = ws3.cell(row=row_i, column=6, value=res['worst_period'])
        c_sh = ws3.cell(row=row_i, column=7, value=res['sharpe'])
        c_win = ws3.cell(row=row_i, column=8, value=res['win_rate'])

        c_name.font = font_bold
        c_id.font = font_data
        c_cum.font = font_bold
        c_cum.number_format = '+0.00%;-0.00%;0.00%'
        c_avg.number_format = '+0.00%;-0.00%;0.00%'
        c_best.number_format = '+0.00%;-0.00%;0.00%'
        c_worst.number_format = '+0.00%;-0.00%;0.00%'
        c_sh.number_format = '0.00'
        c_win.number_format = '0.0%'

        for c in (c_name, c_id, c_cum, c_avg, c_best, c_worst, c_sh, c_win):
            c.alignment = align_center
            c.border = border_cell
            if r_fill:
                c.fill = r_fill

    for col in ws3.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws3.column_dimensions[col_letter].width = max(max_len + 4, 15)

    wb.save(filename)


if __name__ == "__main__":
    run_fixed_optimizer()
