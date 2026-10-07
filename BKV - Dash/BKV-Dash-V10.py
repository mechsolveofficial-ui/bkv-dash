import os
import io
import time
import bisect
from datetime import datetime, timedelta, timezone
import pytz
import jdatetime
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- تنظیمات پایه ---
CSV_FILE_PATH = "dollar_history_expert.csv"
JSON_OUTPUT_PATH = "bkv_data.json"
START_DATE = "2014-01-01"
# رفع مشکل yfinance با اضافه کردن ۱ روز به تاریخ امروز برای دریافت دیتای کامل
END_DATE = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

# --- تنظیمات تحلیل بازه‌های حبابی ---
# پنجره تشخیص قله/دره محلی (بر حسب تعداد نقطه معاملاتی در هر طرف).
# یک نقطه وقتی «قله» است که در بازه [i-w , i+w] بیشترین قیمت را داشته باشد.
SWING_WINDOW = 5

# حداقل تعداد نمونه تاریخی لازم برای اعتبار خروجی.
# چون تعداد بازه‌ها = تعداد نقاط است، هر بازه خیلی باریک می‌شود و ممکن است
# فقط ۱ نقطه داشته باشد. اگر تعداد نمونه کمتر از این عدد باشد، بازه به صورت
# متقارن به بازه‌های همسایه گسترش داده می‌شود تا به این حداقل برسیم.
# اگر دقیقاً همان رفتار خام درخواستی را می‌خواهید، این عدد را ۱ بگذارید.
MIN_SAMPLES_IN_BIN = 8

# افق‌های زمانی تقویمی ثابت برای محاسبه میانگین رشد/نزول قیمت از نقاط هم‌حباب.
# کلیدها فقط برچسب نمایشی هستند؛ مقادیر بر حسب «روز تقویمی» است.
HORIZON_DAYS = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
}


# ==========================================
# تابع کمکی: پر کردن «فقط و فقط» تاریخ هدف (امروز)
# ==========================================
def fill_target_date_only(df_prices, target_date, value_col, label=""):
    """
    این تابع صرفاً برای هم‌تراز کردن «اشتراک تاریخ‌ها در آخرین روز» است.

    منطق:
      1) اگر برای target_date (امروز) قیمت معتبر وجود دارد  ->  هیچ کاری نمی‌کنیم.
      2) اگر وجود ندارد  ->  به عقب برمی‌گردیم، آخرین روزی که قیمت معتبر ثبت شده
         را پیدا می‌کنیم و همان مقدار را *فقط* برای target_date ثبت می‌کنیم.

    ❗ هیچ تاریخ دیگری دست‌کاری نمی‌شود: روزهای میانی و کل تاریخچه دست‌نخورده
       باقی می‌مانند و هیچ ردیف جعلی برای گذشته ساخته نمی‌شود.
    """
    if df_prices is None or df_prices.empty or target_date is None:
        return df_prices

    df = df_prices.copy()
    df['Date_Gregorian'] = pd.to_datetime(df['Date_Gregorian']).dt.date
    df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
    df = df.sort_values('Date_Gregorian').reset_index(drop=True)

    name = label or value_col
    mask_target = df['Date_Gregorian'] == target_date

    # قیمت معتبر = هم NaN نباشد هم صفر/منفی نباشد
    is_valid = df[value_col].notna() & (df[value_col] > 0)

    # --- حالت ۱: منبع خودش برای امروز دیتا دارد ---
    if (mask_target & is_valid).any():
        print(f"   ✅ {name}: دیتای {target_date} از خود منبع موجود است.")
        return df

    # --- برگرد عقب: آخرین روزِ دارای قیمت معتبر قبل از تاریخ هدف ---
    past_valid = df[(df['Date_Gregorian'] < target_date) & is_valid]
    if past_valid.empty:
        print(f"   ⚠️ {name}: هیچ قیمت معتبری برای انتقال به {target_date} پیدا نشد.")
        return df

    last_row = past_valid.iloc[-1]
    last_date = last_row['Date_Gregorian']
    last_val = last_row[value_col]

    if mask_target.any():
        # ردیف امروز هست ولی مقدارش خالی/صفر است -> فقط همان خانه پر می‌شود
        df.loc[mask_target, value_col] = last_val
    else:
        # ردیف امروز وجود ندارد -> فقط یک ردیف برای امروز اضافه می‌شود
        df = pd.concat(
            [df, pd.DataFrame({'Date_Gregorian': [target_date], value_col: [last_val]})],
            ignore_index=True
        )
        df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
        df = df.sort_values('Date_Gregorian').reset_index(drop=True)

    print(f"   🔄 {name}: دیتای {target_date} نبود -> قیمت {last_date} ({last_val:,.2f}) برای امروز ثبت شد.")
    return df


# ==========================================
# تابع کمکی: دانلود سری قیمت از یاهو فایننس
# ==========================================
def download_yahoo_series(ticker, value_col):
    """سری قیمت روزانه را دانلود و به دیتافریم دو ستونه تبدیل می‌کند."""
    df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)

    if df is None or df.empty:
        return pd.DataFrame(columns=['Date_Gregorian', value_col])

    if isinstance(df.columns, pd.MultiIndex):
        df = df['Close'].reset_index()
    else:
        df = df[['Close']].reset_index()

    df = df.iloc[:, :2]
    df.columns = ['Date_Gregorian', value_col]
    df['Date_Gregorian'] = pd.to_datetime(df['Date_Gregorian']).dt.date
    df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
    return df


# ==================================================================
# ➕ بخش جدید: تحلیل «بازه حبابی فعلی» و رفتار تاریخی قیمت پس از آن
# ==================================================================
def _find_swing_points(prices, window):
    """
    قله‌ها و دره‌های محلی «تأییدشده» را پیدا می‌کند.

    نقطه i قله است اگر در پنجره [i-window , i+window] بیشترین مقدار را داشته باشد
    و نقطه i دره است اگر در همان پنجره کمترین مقدار را داشته باشد.
    نقاط ابتدا و انتهای سری که پنجره کاملی ندارند، تأیید نمی‌شوند (چون هنوز
    مشخص نیست اکسترمم محلی هستند یا نه).
    """
    n = len(prices)
    is_peak = np.zeros(n, dtype=bool)
    is_trough = np.zeros(n, dtype=bool)

    if n <= 2 * window:
        return is_peak, is_trough

    for i in range(window, n - window):
        seg = prices[i - window: i + window + 1]
        if prices[i] >= seg.max():
            is_peak[i] = True
        if prices[i] <= seg.min():
            is_trough[i] = True

    return is_peak, is_trough


def _next_extreme_index(flags):
    """
    برای هر اندیس i، اندیس «اولین» نقطه‌ای که flag آن True است و اکیداً بعد از i
    قرار دارد را برمی‌گرداند (این آرایه یک زنجیره‌ی رو-به-جلو بین قله‌ها/دره‌های
    پیاپی می‌سازد: next_peak[j] یعنی «قله تأییدشده‌ی بعدی بعد از قله j»).
    اگر چنین نقطه‌ای وجود نداشته باشد -1 برمی‌گردد.
    """
    n = len(flags)
    nxt = np.full(n, -1, dtype=int)
    last = -1
    for i in range(n - 1, -1, -1):
        nxt[i] = last
        if flags[i]:
            last = i
    return nxt


def _first_profitable_peak(i, prices, next_peak):
    """
    ⚠️ رفع باگ نسبت به نسخه قبلی:
    نسخه قبلی صرفاً «اولین قله تأییدشده» را برمی‌گرداند، بدون توجه به اینکه آیا
    قیمت آن قله واقعاً از قیمت لنگر (i) بالاتر است یا نه. در یک روند نزولی،
    اولین قله تأییدشده می‌تواند یک «سقف پایین‌تر» باشد که هنوز زیر قیمت ورود
    است؛ محاسبه بازده نسبت به آن، عددی *منفی* در ستون «سود» تولید می‌کرد
    (همان چیزی که در داشبورد به‌شکل +-x.xx% دیده می‌شد).

    این تابع در امتداد زنجیره‌ی قله‌های تأییدشده جلو می‌رود تا اولین قله‌ای که
    واقعاً نسبت به قیمت لنگر «سود» محسوب می‌شود (prices[j] > prices[i]) را پیدا
    کند. اگر چنین قله‌ای در کل تاریخچه بعد از i وجود نداشته باشد، -1 برمی‌گردد.
    """
    j = next_peak[i]
    guard = 0
    n = len(prices)
    while j != -1 and prices[j] <= prices[i]:
        j = next_peak[j]
        guard += 1
        if guard > n:
            return -1
    return j


def _first_lossy_trough(i, prices, next_trough):
    """قرینه‌ی _first_profitable_peak برای دره‌ها؛ باید prices[k] < prices[i] باشد."""
    k = next_trough[i]
    guard = 0
    n = len(prices)
    while k != -1 and prices[k] >= prices[i]:
        k = next_trough[k]
        guard += 1
        if guard > n:
            return -1
    return k


def _asof_price(dates_list, prices_arr, target_date):
    """
    قیمت «آخرین روز معتبر تا و شامل target_date» را برمی‌گرداند — دقیقاً همان
    رفتاری که خواسته شد: اگر در target_date قیمتی ثبت نشده (تعطیلی/آخر هفته)،
    برمی‌گردد عقب و آخرین قیمت ثبت‌شده را برمی‌دارد.

    نکته مهم: اگر target_date از آخرین تاریخ موجود در کل سری هم جلوتر باشد
    (یعنی آن افق زمانی هنوز عملاً فرانرسیده، مثلاً می‌خواهیم بازده ۳ ماه بعد
    یک لنگرِ ۱۰ روز پیش را حساب کنیم ولی هنوز ۳ ماه نگذشته)، عمداً None
    برمی‌گردانیم؛ چون جایگزین کردن آن با آخرین قیمت فعلی باعث سوگیری بزرگ در
    میانگین می‌شد (یک بازه ۳ ماهه با داده‌ی فقط ۱۰ روزه اندازه‌گیری می‌شد).
    """
    if target_date > dates_list[-1]:
        return None, None
    idx = bisect.bisect_right(dates_list, target_date) - 1
    if idx < 0:
        return None, None
    p = float(prices_arr[idx])
    if not np.isfinite(p) or p <= 0:
        return None, None
    return p, dates_list[idx]


def analyze_bubble_bin(df, label="", swing_window=SWING_WINDOW, min_samples=MIN_SAMPLES_IN_BIN,
                        horizons_days=None):
    """
    منطق:
      1) کل گستره حباب تاریخی (از مینیمم تا ماکسیمم) به تعداد «کل نقاط قیمتی»
         بازه مساوی تقسیم می‌شود. پس گام هر بازه = (max-min)/N است.
      2) مشخص می‌شود حباب امروز در کدام بازه قرار دارد. اگر حباب خارج از گستره
         باشد (کمتر از min یا بیشتر از max) به نزدیک‌ترین بازه (اولین یا آخرین)
         نسبت داده می‌شود.
      3) تمام روزهای تاریخچه که حبابشان در همان بازه بوده به عنوان «نقطه لنگر»
         انتخاب می‌شوند (با گسترش متقارن بازه در صورت کمبود نمونه).
      4) برای هر لنگر دو نوع محاسبه انجام می‌شود:
         الف) اولین قله محلیِ *واقعاً سودآور* بعد از آن (زودترین ماکسیمم سود
              محلی که بازده‌اش مثبت است) و اولین دره محلیِ *واقعاً ضررده* بعد
              از آن (زودترین ضرر محلی که بازده‌اش منفی است) پیدا می‌شود.
              [رفع باگ نسخه قبلی: قبلاً ممکن بود «سود» منفی یا «ضرر» مثبت
              گزارش شود، چون فقط تأییدشدگی قله/دره چک می‌شد نه علامت بازده]
         ب) بازده میانگین در افق‌های زمانی تقویمی *ثابت* (پیش‌فرض ۱، ۷، ۳۰ و
            ۹۰ روز) هم محاسبه می‌شود؛ اگر دقیقاً همان روز قیمتی ثبت نشده
            باشد (تعطیلی/آخر هفته)، آخرین قیمت ثبت‌شده قبل از آن روز لحاظ
            می‌شود.
      5) میانگین (و میانه) این مقادیر روی همه لنگرها گزارش می‌شود؛ همه‌ی
         زمان‌ها بر حسب «روز تقویمی» هستند، نه روز معاملاتی.
    """
    if horizons_days is None:
        horizons_days = HORIZON_DAYS

    d = df.reset_index(drop=True)
    prices = pd.to_numeric(d['IME_Price'], errors='coerce').to_numpy(dtype=float)
    bubbles = pd.to_numeric(d['Bubble_Pct'], errors='coerce').to_numpy(dtype=float)
    dates = pd.to_datetime(d['Date_Gregorian']).dt.date.tolist()
    n = len(d)

    if n < (2 * swing_window + 3):
        print(f"   ⚠️ {label}: تعداد نقاط برای تحلیل بازه حبابی کافی نیست.")
        return None

    min_b = float(np.nanmin(bubbles))
    max_b = float(np.nanmax(bubbles))
    cur_b = float(bubbles[-1])

    # --- ۱) تقسیم گستره حباب به N بازه (N = تعداد کل نقاط) ---
    n_bins = n
    if max_b > min_b:
        step = (max_b - min_b) / n_bins
        bin_of = np.clip(np.floor((bubbles - min_b) / step).astype(int), 0, n_bins - 1)
        cur_bin = int(np.clip(int(np.floor((cur_b - min_b) / step)), 0, n_bins - 1))
    else:
        step = 0.0
        bin_of = np.zeros(n, dtype=int)
        cur_bin = 0

    # --- ۲) شناسایی قله‌ها و دره‌های محلی ---
    is_peak, is_trough = _find_swing_points(prices, swing_window)
    next_peak = _next_extreme_index(is_peak)
    next_trough = _next_extreme_index(is_trough)

    # --- ۳) انتخاب نقاط لنگر داخل بازه حبابی فعلی (با گسترش در صورت کمبود نمونه) ---
    # معیار «قابل استفاده بودن» یک لنگر: حداقل یکی از «قله سودآور بعدی» یا
    # «دره ضررده بعدی» برایش واقعاً قابل محاسبه باشد (نه فقط وجود یک قله/دره
    # تأییدشده بدون توجه به علامت بازده‌اش).
    def _count_usable(idx_array):
        cnt = 0
        for i in idx_array:
            i = int(i)
            if not np.isfinite(prices[i]) or prices[i] <= 0:
                continue
            pk = _first_profitable_peak(i, prices, next_peak)
            tr = _first_lossy_trough(i, prices, next_trough)
            if pk != -1 or tr != -1:
                cnt += 1
        return cnt

    radius = 0
    while True:
        mask = (bin_of >= cur_bin - radius) & (bin_of <= cur_bin + radius)
        anchors = np.where(mask)[0]
        if _count_usable(anchors) >= min_samples or radius >= n_bins:
            break
        radius += 1

    bin_low = min_b + max(cur_bin - radius, 0) * step
    bin_high = min_b + min(cur_bin + radius + 1, n_bins) * step

    # --- ۴الف) محاسبه اولین سود و اولین ضرر اکسترمم *واقعی* بعد از هر لنگر ---
    profits, profit_days = [], []
    losses, loss_days = [], []

    # --- ۴ب) محاسبه بازده میانگین در افق‌های زمانی تقویمی ثابت ---
    horizon_returns = {key: [] for key in horizons_days}

    for i in anchors:
        i = int(i)
        if not np.isfinite(prices[i]) or prices[i] <= 0:
            continue

        j = _first_profitable_peak(i, prices, next_peak)
        if j != -1:
            profits.append((prices[j] / prices[i] - 1.0) * 100.0)
            profit_days.append((dates[j] - dates[i]).days)

        k = _first_lossy_trough(i, prices, next_trough)
        if k != -1:
            losses.append((prices[k] / prices[i] - 1.0) * 100.0)
            loss_days.append((dates[k] - dates[i]).days)

        for key, h in horizons_days.items():
            target_date = dates[i] + timedelta(days=h)
            p_t, _used_date = _asof_price(dates, prices, target_date)
            if p_t is None:
                continue
            horizon_returns[key].append((p_t / prices[i] - 1.0) * 100.0)

    def _stat(arr):
        if not arr:
            return None
        return round(float(np.mean(arr)), 2)

    def _median(arr):
        if not arr:
            return None
        return round(float(np.median(arr)), 2)

    horizons_result = {}
    for key, h in horizons_days.items():
        arr = horizon_returns[key]
        horizons_result[key] = {
            "days": h,
            "avg_return_pct": _stat(arr),
            "median_return_pct": _median(arr),
            "sample_count": len(arr),
        }

    result = {
        # وضعیت فعلی
        "current_bubble_pct": round(cur_b, 2),
        "min_bubble_pct": round(min_b, 2),
        "max_bubble_pct": round(max_b, 2),
        "total_points": int(n),
        "bin_step_pct": round(step, 5),
        "bin_index": int(cur_bin),
        "bin_range_pct": [round(bin_low, 3), round(bin_high, 3)],
        "bin_expanded_by": int(radius),      # اگر 0 باشد یعنی دقیقاً همان بازه خام
        "matched_points": int(len(anchors)),

        # ۴ خروجی اصلی درخواستی (اصلاح‌شده: علامت‌ها دیگر با نام ستون ناسازگار نیستند)
        "avg_first_peak_return_pct": _stat(profits),     # میانگین درصد سود واقعی (همیشه ≥ 0)
        "avg_days_to_first_peak": _stat(profit_days),    # میانگین روز تقویمی تا آن سود
        "avg_first_trough_return_pct": _stat(losses),    # میانگین درصد ضرر واقعی (همیشه ≤ 0)
        "avg_days_to_first_trough": _stat(loss_days),    # میانگین روز تقویمی تا آن ضرر

        # آمار تکمیلی (میانه، برای کاهش اثر داده‌های پرت)
        "median_first_peak_return_pct": _median(profits),
        "median_days_to_first_peak": _median(profit_days),
        "median_first_trough_return_pct": _median(losses),
        "median_days_to_first_trough": _median(loss_days),

        "peak_samples": len(profits),
        "trough_samples": len(losses),
        "swing_window": swing_window,

        # ➕ بازده میانگین در افق‌های زمانی تقویمی ثابت (۱روز/۱هفته/۱ماه/۳ماه)
        # از همان نقاط هم‌حباب (anchors) محاسبه شده تا با بخش بالا سازگار باشد.
        "horizons": horizons_result,
    }

    print(f"   🎯 {label} | حباب فعلی {cur_b:.2f}% -> بازه #{cur_bin} "
          f"[{bin_low:.3f}% تا {bin_high:.3f}%] | {len(anchors)} نقطه مشابه"
          + (f" (بازه {radius} پله گسترش یافت)" if radius else ""))
    if profits:
        print(f"      📈 میانگین اولین سود اکسترمم واقعی: {result['avg_first_peak_return_pct']:+.2f}% "
              f"پس از {result['avg_days_to_first_peak']:.1f} روز تقویمی ({len(profits)} نمونه)")
    if losses:
        print(f"      📉 میانگین اولین ضرر اکسترمم واقعی: {result['avg_first_trough_return_pct']:+.2f}% "
              f"پس از {result['avg_days_to_first_trough']:.1f} روز تقویمی ({len(losses)} نمونه)")
    for key in ("1d", "1w", "1m", "3m"):
        hr = horizons_result.get(key)
        if hr and hr["avg_return_pct"] is not None:
            print(f"      🗓️ بازده میانگین افق {key}: {hr['avg_return_pct']:+.2f}% "
                  f"({hr['sample_count']} نمونه)")

    return result


# ==========================================
# نصب chromedriver با فال‌بک میرور
# (برای شبکه‌هایی که به storage.googleapis.com دسترسی ندارند — مثلاً ایران)
# ==========================================
CHROMEDRIVER_MIRRORS = [
    "https://cdn.npmmirror.com/binaries/chrome-for-testing",
]


def _get_installed_chrome_version():
    """نسخه Chrome نصب‌شده روی سیستم را برمی‌گرداند (مثل 154.0.8037.92)."""
    import sys as _sys
    if _sys.platform.startswith("win"):
        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Google\Chrome\BLBeacon") as key:
                        value, _ = winreg.QueryValueEx(key, "version")
                        if value:
                            return value.strip()
                except OSError:
                    continue
        except Exception:
            pass
        return None
    try:
        import subprocess
        out = subprocess.run(
            ["google-chrome", "--version"], capture_output=True, text=True, timeout=10
        ).stdout
        return out.strip().split()[-1] if out.strip() else None
    except Exception:
        return None


def _pick_mirror_driver_version(chrome_version, session):
    """از لیست نسخه‌های موجود در میرور، نزدیک‌ترین نسخه chromedriver سازگار را
    انتخاب می‌کند (همان major و ترجیحاً همان build — chromedriver فقط major را چک می‌کند).
    اگر لیست در دسترس نبود، همان نسخه کروم نصب‌شده برگردانده می‌شود."""
    import re
    try:
        listing = session.get(
            "https://registry.npmmirror.com/-/binary/chrome-for-testing/", timeout=30
        ).json()
    except Exception:
        return chrome_version
    versions = []
    for item in listing:
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d+)/?", str(item.get("name", "")))
        if m:
            versions.append(tuple(int(g) for g in m.groups()))
    if not versions:
        return chrome_version
    target = tuple(int(p) for p in chrome_version.split("."))
    same_build = [v for v in versions if v[:3] == target[:3]]
    pool = same_build or [v for v in versions if v[0] == target[0]]
    lower = [v for v in pool if v <= target]
    return ".".join(map(str, max(lower or pool)))


def _install_chromedriver_with_mirror(chrome_version):
    """دانلود chromedriver از میرور جایگزین (قابل دسترس در ایران) با کش محلی."""
    import zipfile
    import platform

    sysname = platform.system()
    if sysname == "Windows":
        plat = "win64"
        zip_name = "chromedriver-win64.zip"
        exe_rel = os.path.join("chromedriver-win64", "chromedriver.exe")
    elif sysname == "Darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        plat = f"mac-{arch}"
        zip_name = f"chromedriver-mac-{arch}.zip"
        exe_rel = os.path.join(f"chromedriver-mac-{arch}", "chromedriver")
    else:
        plat = "linux64"
        zip_name = "chromedriver-linux64.zip"
        exe_rel = os.path.join("chromedriver-linux64", "chromedriver")

    cache_dir = os.path.join(os.path.expanduser("~"), ".wdm-mirror", chrome_version)
    driver_path = os.path.join(cache_dir, exe_rel)
    if os.path.exists(driver_path):
        print(f"   ✅ chromedriver از کش میرور استفاده شد.")
        return driver_path

    session = requests.Session()
    best = _pick_mirror_driver_version(chrome_version, session)
    if best != chrome_version:
        print(f"   ℹ️ نزدیک‌ترین نسخه سازگار در میرور: {best} (کروم نصب‌شده: {chrome_version})")
    candidate_versions = [best] if best == chrome_version else [best, chrome_version]

    last_err = None
    for ver in candidate_versions:
        cache_dir_ver = os.path.join(os.path.expanduser("~"), ".wdm-mirror", ver)
        driver_path = os.path.join(cache_dir_ver, exe_rel)
        if os.path.exists(driver_path):
            print(f"   ✅ chromedriver {ver} از کش میرور استفاده شد.")
            return driver_path
        url = f"{CHROMEDRIVER_MIRRORS[0]}/{ver}/{plat}/{zip_name}"
        try:
            print(f"   🔄 دانلود chromedriver از میرور: {url}")
            resp = session.get(url, timeout=(10, 300))
            resp.raise_for_status()
            os.makedirs(cache_dir_ver, exist_ok=True)
            zip_path = os.path.join(cache_dir_ver, zip_name)
            with open(zip_path, "wb") as f:
                f.write(resp.content)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(cache_dir_ver)
            os.remove(zip_path)
            if sysname != "Windows":
                os.chmod(driver_path, 0o755)
            print(f"   ✅ chromedriver {ver} از میرور نصب شد ({plat}).")
            return driver_path
        except Exception as e:
            last_err = e
            print(f"   ⚠️ دانلود نسخه {ver} ناموفق: {e}")
    raise RuntimeError(f"دانلود chromedriver از میرورها ناموفق بود: {last_err}")


# ==========================================
# بخش اول: اسکرپر افزایشی دلار
# ==========================================
def scrape_dollar_history(file_name=CSV_FILE_PATH):
    last_scraped_date = None
    existing_df = None

    if os.path.exists(file_name):
        try:
            existing_df = pd.read_csv(file_name)
            if not existing_df.empty and 'Date_Gregorian' in existing_df.columns:
                existing_df['Date_Gregorian_Parsed'] = pd.to_datetime(existing_df['Date_Gregorian'], format='mixed').dt.date
                last_scraped_date = existing_df['Date_Gregorian_Parsed'].max()
                print(f"📊 فایل دیتابیس قبلی پیدا شد. آخرین تاریخ: {last_scraped_date}")
        except Exception as e:
            print(f"⚠️ خطا در خواندن فایل قبلی: {e}")

    chrome_options = Options()
    # اجرای مرورگر در بک‌گراند (بدون پنجره ویزیبل)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    # لازم برای اجرای Chrome در محیط‌های CI/کانتینر (GitHub Actions و Colab)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

    try:
        driver_path = ChromeDriverManager().install()
    except Exception as dm_err:
        # در برخی شبکه‌ها (مثلاً ایران) دانلود از storage.googleapis.com مسدود است؛
        # در این حالت chromedriver از میرور جایگزین دانلود می‌شود.
        print(f"⚠️ دانلود رسمی chromedriver ناموفق بود ({type(dm_err).__name__}). تلاش با میرور جایگزین…")
        chrome_version = _get_installed_chrome_version()
        if not chrome_version:
            raise
        driver_path = _install_chromedriver_with_mirror(chrome_version)
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    url = "https://www.tgju.org/profile/price_dollar_rl/history"
    driver.get(url)
    wait = WebDriverWait(driver, 20)

    new_data_from_table = []
    live_df = None

    try:
        print("⏳ در حال استخراج قیمت لحظه‌ای امروز از هدر...")
        try:
            wait.until(lambda d: d.find_element(By.CSS_SELECTOR, 'span[data-col="info.last_trade.PDrCotVal"]').get_attribute("textContent").strip() != '')
            live_price_element = driver.find_element(By.CSS_SELECTOR, 'span[data-col="info.last_trade.PDrCotVal"]')
            live_price = live_price_element.get_attribute("textContent").replace(',', '').strip()

            tehran_tz = pytz.timezone('Asia/Tehran')
            now_tehran = datetime.now(tehran_tz)
            live_gregorian = now_tehran.strftime('%Y-%m-%d')
            live_jalali = jdatetime.date.fromgregorian(date=now_tehran).strftime('%Y/%m/%d')

            if live_price:
                live_df = pd.DataFrame([{
                    'Open': live_price,
                    'Low': live_price,
                    'High': live_price,
                    'Close': live_price,
                    'Change': '0',
                    'Change_Percent': '0',
                    'Date_Gregorian': live_gregorian,
                    'Date_Jalali': live_jalali
                }])
                print(f"✅ قیمت لحظه‌ای ({live_price}) برای {live_jalali} استخراج شد.")
        except Exception as e:
            print("⚠️ دریافت قیمت لحظه‌ای با مشکل مواجه شد. فقط از جدول استفاده می‌شود.")

        page_num = 1
        while True:
            print(f"🔄 در حال بررسی جدول سایت - صفحه {page_num}...")

            wait.until(EC.presence_of_element_located((By.ID, "DataTables_Table_0")))
            info_before = driver.find_element(By.ID, "DataTables_Table_0_info").text

            html_content = driver.page_source
            df_page = pd.read_html(io.StringIO(html_content), attrs={'id': 'DataTables_Table_0'})[0]

            if df_page.shape[1] >= 8:
                df_page = df_page.iloc[:, :8]
                df_page.columns = ['Open', 'Low', 'High', 'Close', 'Change', 'Change_Percent', 'Date_Gregorian', 'Date_Jalali']

            stop_scraping = False

            if last_scraped_date is not None:
                df_page['temp_date'] = pd.to_datetime(df_page['Date_Gregorian'], format='mixed').dt.date
                mask = df_page['temp_date'] <= last_scraped_date

                if mask.any():
                    match_idx = mask.idxmax()
                    safe_idx = min(match_idx + 2, len(df_page))
                    df_new_only = df_page.iloc[:safe_idx].drop(columns=['temp_date'])

                    if not df_new_only.empty:
                        new_data_from_table.append(df_new_only)

                    print("🛑 به رکوردهای تکراری رسیدیم. اسکرپینگ متوقف شد.")
                    stop_scraping = True
                else:
                    new_data_from_table.append(df_page.drop(columns=['temp_date']))
            else:
                new_data_from_table.append(df_page)

            if stop_scraping:
                break

            try:
                try:
                    next_button = driver.find_element(By.ID, "DataTables_Table_0_next")
                except:
                    next_button = driver.find_element(By.XPATH, f"//a[@aria-controls='DataTables_Table_0' and @data-dt-idx='{page_num + 1}']")

                if next_button.get_attribute("class") and "disabled" in next_button.get_attribute("class"):
                    print("🛑 به آخرین صفحه موجود سایت رسیدیم.")
                    break

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", next_button)

                wait.until(lambda d: d.find_element(By.ID, "DataTables_Table_0_info").text != info_before)
                time.sleep(1)
            except Exception as e:
                print("❌ پایان صفحات.")
                break

            page_num += 1

    finally:
        driver.quit()

    # ادغام نهایی
    all_chunksToConcat = []
    if new_data_from_table:
        all_chunksToConcat.append(pd.concat(new_data_from_table, ignore_index=True))
    if live_df is not None:
        all_chunksToConcat.append(live_df)
    if existing_df is not None:
        if 'Date_Gregorian_Parsed' in existing_df.columns:
            existing_df = existing_df.drop(columns=['Date_Gregorian_Parsed'])
        all_chunksToConcat.append(existing_df)

    if all_chunksToConcat:
        final_df = pd.concat(all_chunksToConcat, ignore_index=True)
        final_df['Date_Gregorian'] = pd.to_datetime(final_df['Date_Gregorian'], format='mixed').dt.strftime('%Y-%m-%d')
        final_df = final_df.drop_duplicates(subset=['Date_Gregorian'], keep='first')
        final_df = final_df.sort_values(by='Date_Gregorian', ascending=False).reset_index(drop=True)

        cols_to_fix = ['Open', 'Low', 'High', 'Close', 'Change']
        for col in cols_to_fix:
            final_df[col] = pd.to_numeric(final_df[col].astype(str).str.replace(',', ''), errors='coerce')

        return final_df
    else:
        return existing_df


# ==========================================
# بخش دوم: پردازش کالاها و ایجاد JSON
# ==========================================
def process_commodity(ime_code, global_ticker, unit_factor, label, unit_name, df_dollar, df_gold, target_date, is_oil_based=False, ime_multiplier=1, coin_gold_weight=None):
    print(f"--- پردازش داده‌های {label} ---")
    start_ts = int(time.mktime(datetime.strptime(START_DATE, "%Y-%m-%d").timetuple()))
    # یک روز جلوتر تا اگر API کندل امروز را دارد، حتماً برگردانده شود
    end_ts = int(time.mktime((datetime.now() + timedelta(days=1)).timetuple()))

    url_ime = f"https://imechartapi.tadbirrlc.com/imechartdata/history?symbol={ime_code}&resolution=D&from={start_ts}&to={end_ts}"
    res_ime = requests.get(url_ime).json()

    if res_ime.get('s') != 'ok':
        print(f"خطا در دریافت داده بورس کالا برای {label}")
        return None

    df_ime = pd.DataFrame({
        'Date_Gregorian': [datetime.fromtimestamp(ts, tz=timezone.utc).date() for ts in res_ime['t']],
        'IME_Price': res_ime['c']
    })
    df_ime['IME_Price'] = pd.to_numeric(df_ime['IME_Price'], errors='coerce') * ime_multiplier
    df_ime = df_ime.drop_duplicates(subset=['Date_Gregorian'], keep='last')

    # ✅ فقط اگر بورس کالا برای «امروز» دیتا نداشت، آخرین قیمت ثبت‌شده را برای امروز می‌گذاریم
    df_ime = fill_target_date_only(df_ime, target_date, 'IME_Price', label=f"بورس کالا ({label})")

    df_global = download_yahoo_series(global_ticker, 'Global_USD')
    if df_global.empty:
        print(f"❌ دیتای بازار جهانی برای {label} ({global_ticker}) خالی برگشت. این کالا رد شد.")
        return None

    # ✅ همان منطق برای بازار بین‌الملل
    df_global = fill_target_date_only(df_global, target_date, 'Global_USD', label=f"بازار جهانی ({global_ticker})")

    df = pd.merge(df_ime, df_dollar, on='Date_Gregorian', how='inner')
    df = pd.merge(df, df_global, on='Date_Gregorian', how='inner')
    df = pd.merge(df, df_gold, on='Date_Gregorian', how='inner')

    if coin_gold_weight:
        df['Global_Price_Rial'] = (df['Global_USD'] / 31.1035) * coin_gold_weight * df['USD_Rate']
    elif is_oil_based:
        df['Global_Price_Rial'] = (df['Global_USD'] * unit_factor / 1000) * df['USD_Rate']
    else:
        df['Global_Price_Rial'] = (df['Global_USD'] / unit_factor) * df['USD_Rate']

    df['Bubble_Pct'] = ((df['IME_Price'] - df['Global_Price_Rial']) / df['Global_Price_Rial']) * 100
    df['Gold_Ratio'] = df['Global_USD'] / df['Gold_Ounce_USD']
    df = df.sort_values('Date_Gregorian').dropna()

    if df.empty:
        print(f"❌ اشتراک تاریخ‌ها برای {label} خالی شد.")
        return None

    # ==============================================================
    # ➕ محاسبه چارک (Q) و فاصله نسبی (x) برای حباب فعلی
    # ==============================================================
    # چون دیتافریم مرتب شده است، آخرین ردیف برابر با اطلاعات حباب فعلی (روز آخر) است.
    current_bubble = df['Bubble_Pct'].iloc[-1]

    # محاسبه مقادیر آماری از کل حباب‌های تاریخچه
    min_bubble = df['Bubble_Pct'].min()
    max_bubble = df['Bubble_Pct'].max()
    q1 = df['Bubble_Pct'].quantile(0.25)
    q2 = df['Bubble_Pct'].quantile(0.50)
    q3 = df['Bubble_Pct'].quantile(0.75)

    # 1. محاسبه موقعیت چارکی (Q)
    if current_bubble <= q1:
        q_label = "Q0Q1"
    elif current_bubble <= q2:
        q_label = "Q1Q2"
    elif current_bubble <= q3:
        q_label = "Q2Q3"
    else:
        q_label = "Q3Q4"

    # 2. محاسبه موقعیت فاصله (x)
    if max_bubble > min_bubble:
        x_val = (current_bubble - min_bubble) / (max_bubble - min_bubble)
    else:
        x_val = 0.5  # جلوگیری از خطای تقسیم بر صفر در صورتی که ماکزیمم و مینیمم برابر باشند

    print(f"   📊 وضعیت حباب فعلی ({current_bubble:.2f}%): چارک {q_label} | مقدار x = {x_val:.4f}")
    # ==============================================================

    # ➕ تحلیل بازه حبابی: رفتار تاریخی قیمت پس از قرار گرفتن در همین بازه حباب
    bin_forecast = analyze_bubble_bin(df, label=label)

    print(f"   📅 آخرین تاریخ اشتراک {label}: {df.iloc[-1]['Date_Gregorian']} / {df.iloc[-1]['Date_Jalali']}")

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row['Date_Jalali']),
            "ime_price": round(row['IME_Price'], 2),
            "global_rial": round(row['Global_Price_Rial'], 2),
            "bubble_pct": round(row['Bubble_Pct'], 2),
            "global_usd": round(row['Global_USD'], 2),
            "gold_ratio": round(row['Gold_Ratio'], 4)
        })

    df_global_hist = df_global.copy()
    df_global_hist = pd.merge(df_global_hist, df_gold, on='Date_Gregorian', how='inner')
    df_global_hist['Gold_Ratio'] = df_global_hist['Global_USD'] / df_global_hist['Gold_Ounce_USD']
    df_global_hist['YearMonth'] = pd.to_datetime(df_global_hist['Date_Gregorian']).dt.to_period('M')
    df_global_hist = df_global_hist.groupby('YearMonth').last().reset_index()

    hist_records = []
    for _, row in df_global_hist.iterrows():
        hist_records.append({
             "date": str(row['Date_Gregorian']),
             "global_usd": round(row['Global_USD'], 2),
             "gold_ratio": round(row['Gold_Ratio'], 4),
             "bubble_pct": 0,
             "ime_price": 0,
             "global_rial": 0
        })

    # خروجی جدید شامل کلید bubble_analysis برای متغیرهای درخواست شده
    return {
        "main": records,
        "historical": hist_records,
        "bubble_analysis": {
            "Q": q_label,
            "x": round(x_val, 4)  # گرد شده تا 4 رقم اعشار برای دقت بیشتر در بک‌اِند
        },
        "bin_forecast": bin_forecast
    }


# ==========================================
# اجرای یکپارچه‌ی پایپ‌لاین
# ==========================================
if __name__ == "__main__":
    print(">>> فاز اول: آپدیت دیتابیس دلار")
    df_dollar_raw = scrape_dollar_history(CSV_FILE_PATH)

    if df_dollar_raw is not None:
        df_dollar_raw.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8-sig')
        print(f"💾 دیتابیس دلار با {len(df_dollar_raw)} رکورد بروزرسانی و ذخیره شد.")

        # آماده‌سازی دیتافریم دلار برای پردازش کالاها
        df_dollar = df_dollar_raw.copy()
        df_dollar['Date_Gregorian'] = pd.to_datetime(df_dollar['Date_Gregorian']).dt.date
        df_dollar = df_dollar[['Date_Gregorian', 'Date_Jalali', 'Close']].rename(columns={'Close': 'USD_Rate'})

        # دلار مرجع است؛ پس فقط روزهایی که نرخ معتبر دارند نگه داشته می‌شوند
        df_dollar['USD_Rate'] = pd.to_numeric(df_dollar['USD_Rate'], errors='coerce')
        df_dollar = df_dollar.dropna(subset=['Date_Gregorian', 'USD_Rate'])
        df_dollar = df_dollar[df_dollar['USD_Rate'] > 0]
        df_dollar = df_dollar.drop_duplicates(subset=['Date_Gregorian'], keep='first')

        # تاریخ هدف = جدیدترین روزی که دلار برایش نرخ دارد (معمولاً امروز)
        target_date = df_dollar['Date_Gregorian'].max()
        print(f"🎯 تاریخ هدف (آخرین روز دلار): {target_date} / {jdatetime.date.fromgregorian(date=target_date).strftime('%Y/%m/%d')}")

        print("\n>>> فاز دوم: دریافت دیتای طلا و کالاها")
        print("در حال دریافت داده‌های اونس جهانی طلا...")
        df_gold = download_yahoo_series("GC=F", 'Gold_Ounce_USD')

        if df_gold.empty:
            print("❌ دریافت اونس طلا با شکست مواجه شد. اجرا متوقف شد.")
            raise SystemExit(1)

        # ✅ همان منطق برای اونس طلا (مرجع محاسبه Gold_Ratio است)
        df_gold = fill_target_date_only(df_gold, target_date, 'Gold_Ounce_USD', label="اونس طلا (GC=F)")

        commodity_list = [
            (41, 'GC=F', 31.1035, 'gold_995', 'Gram', False, 10, None),
            (42, 'GC=F', 31.1035, 'gold_coin', 'Coin', False, 1, 7.322),
            (43, 'SI=F', 31.1035, 'silver', 'Gram', False, 1, None),
            (44, 'HG=F', 0.45359, 'copper', 'Kg', False, 1, None),
            (46, 'ZNC=F', 1000, 'zinc', 'Kg', False, 1, None),
            (48, 'TIO=F', 1000, 'iron', 'Kg', False, 1, None),
            (45, 'BZ=F', 7.33, 'bitumen', 'Kg', True, 1, None)
        ]

        output_json = {}
        for item in commodity_list:
            try:
                data = process_commodity(item[0], item[1], item[2], item[3], item[4], df_dollar, df_gold, target_date, item[5], item[6], item[7])
                if data:
                    output_json[item[3]] = data
            except Exception as e:
                print(f"خطا در {item[3]}: {e}")

        # ذخیره فایل نهایی
        with open(JSON_OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(output_json, f, ensure_ascii=False, indent=2)

        # ==========================================
        # جدول خلاصه تحلیل بازه حبابی برای همه نمادها
        # ==========================================
        print("\n" + "=" * 78)
        print("خلاصه تحلیل بازه حبابی (بر اساس قیمت آخرین روز هر نماد)")
        print("=" * 78)
        header = f"{'نماد':<12}{'حباب':>9}{'سود%':>10}{'روز':>8}{'ضرر%':>10}{'روز':>8}{'نمونه':>8}"
        print(header)
        print("-" * 78)
        for key, data in output_json.items():
            bf = data.get("bin_forecast")
            if not bf:
                print(f"{key:<12}{'-':>9}{'داده ناکافی':>44}")
                continue
            print(f"{key:<12}"
                  f"{bf['current_bubble_pct']:>9.2f}"
                  f"{(bf['avg_first_peak_return_pct'] if bf['avg_first_peak_return_pct'] is not None else 0):>10.2f}"
                  f"{(bf['avg_days_to_first_peak'] if bf['avg_days_to_first_peak'] is not None else 0):>8.1f}"
                  f"{(bf['avg_first_trough_return_pct'] if bf['avg_first_trough_return_pct'] is not None else 0):>10.2f}"
                  f"{(bf['avg_days_to_first_trough'] if bf['avg_days_to_first_trough'] is not None else 0):>8.1f}"
                  f"{bf['matched_points']:>8}")
        print("=" * 78)

        # ==========================================
        # جدول خلاصه بازده میانگین در افق‌های زمانی تقویمی ثابت (۱روز/۱هفته/۱ماه/۳ماه)
        # ==========================================
        print("\n" + "=" * 78)
        print("خلاصه بازده میانگین در افق‌های زمانی ثابت (از نقاط هم‌حباب تاریخی)")
        print("=" * 78)
        header2 = f"{'نماد':<12}{'1 روز':>10}{'1 هفته':>10}{'1 ماه':>10}{'3 ماه':>10}{'نمونه':>8}"
        print(header2)
        print("-" * 78)
        for key, data in output_json.items():
            bf = data.get("bin_forecast")
            hz = bf.get("horizons") if bf else None
            if not hz:
                print(f"{key:<12}{'داده ناکافی':>50}")
                continue

            def _fmt(h_key):
                v = hz.get(h_key, {}).get("avg_return_pct")
                return f"{v:+.2f}%" if v is not None else "-"

            print(f"{key:<12}{_fmt('1d'):>10}{_fmt('1w'):>10}{_fmt('1m'):>10}{_fmt('3m'):>10}{bf['matched_points']:>8}")
        print("=" * 78)

        print(f"\n✅ پردازش کامل شد. فایل '{JSON_OUTPUT_PATH}' با موفقیت تولید شد!")

    else:
        print("❌ استخراج دیتای دلار با شکست مواجه شد. اجرای پردازش متوقف گردید.")