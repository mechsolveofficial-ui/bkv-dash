import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Dashboard } from './components/Dashboard';
import { BkvData } from './types';
import { Code2, RefreshCw, PlayCircle, KeyRound, X, Check } from 'lucide-react';
import { PYTHON_SCRIPT } from './PythonScript';

// =====================================================================
// ⚙️ آدرس دیتای خودکار — خروجی GitHub Actions روی برنچ `data`
// =====================================================================
const DATA_BASE_URL = 'https://raw.githubusercontent.com/mechsolveofficial-ui/bkv-data/data';
const GITHUB_REPO = ((import.meta as any).env?.VITE_GITHUB_REPO as string) || 'mechsolveofficial-ui/bkv-dash';
const GITHUB_WORKFLOW = 'update-data.yml';
const RUN_ENDPOINT = '/.netlify/functions/trigger-bkv';

// هماهنگ با زمان‌بندی GitHub Actions (هر ۵ دقیقه)
const AUTO_REFRESH_MS = 5 * 60 * 1000;

type DataSource = 'auto' | 'manual' | null;
type AutoStatus = 'idle' | 'loading' | 'ok' | 'error';
type RunStatus = 'idle' | 'starting' | 'running' | 'ok' | 'error';

const RUN_ERROR_MESSAGES: Record<string, string> = {
  not_configured: 'توکن گیت‌هاب تنظیم نشده است. روی آیکون کلید کلیک کنید.',
  invalid_token: 'توکن گیت‌هاب نامعتبر است یا دسترسی‌های لازم (repo و workflow) را ندارد.',
  github_error: 'اجرای پایپ‌لاین در GitHub شروع نشد. وضعیت اینترنت یا توکن را بررسی کنید.',
};

// نمایش تاریخ/ساعت به وقت تهران با تقویم شمسی (بدون کتابخانه اضافه)
const formatTehranTime = (iso: string): string => {
  try {
    return new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
      timeZone: 'Asia/Tehran',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
};

export default function App() {
  const [data, setData] = useState<BkvData | null>(null);
  const [source, setSource] = useState<DataSource>(null);
  const [lastUpdateIso, setLastUpdateIso] = useState<string | null>(null);
  const [autoStatus, setAutoStatus] = useState<AutoStatus>('idle');
  // پس از آپلود دستی، دریافت خودکار متوقف می‌شود تا دیتای دستی جایگزین نشود
  const [autoPaused, setAutoPaused] = useState(false);
  const [showScript, setShowScript] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus>('idle');
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [githubToken, setGithubToken] = useState<string>(
    () => localStorage.getItem('bkv_github_token') || ((import.meta as any).env?.VITE_GITHUB_TOKEN as string) || ''
  );
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [tempTokenInput, setTempTokenInput] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const autoPausedRef = useRef(false);

  const dataUrlConfigured = !DATA_BASE_URL.includes('USERNAME/REPO');

  useEffect(() => {
    autoPausedRef.current = autoPaused;
  }, [autoPaused]);

  const fetchAutoData = useCallback(async () => {
    if (!dataUrlConfigured) {
      setAutoStatus('error');
      return;
    }
    setAutoStatus('loading');
    try {
      const bust = `?t=${Date.now()}`;
      const [jsonRes, metaRes] = await Promise.all([
        fetch(`${DATA_BASE_URL}/bkv_data.json${bust}`),
        fetch(`${DATA_BASE_URL}/meta.json${bust}`).catch(() => null),
      ]);
      if (!jsonRes.ok) throw new Error(`HTTP ${jsonRes.status}`);
      const json = (await jsonRes.json()) as BkvData;
      let iso: string | null = null;
      if (metaRes && metaRes.ok) {
        const meta = await metaRes.json().catch(() => null);
        iso = meta?.generated_at_utc ?? null;
      }
      setData(json);
      setSource('auto');
      setLastUpdateIso(iso);
      setAutoStatus('ok');
    } catch {
      setAutoStatus('error');
    }
  }, [dataUrlConfigured]);

  // دریافت اولین دیتا + بروزرسانی خودکار هر ۵ دقیقه (هماهنگ با Actions)
  useEffect(() => {
    fetchAutoData();
    const id = setInterval(() => {
      if (!autoPausedRef.current) fetchAutoData();
    }, AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchAutoData]);

  // ── ارسال درخواست اجرای پایپ‌لاین (اول از Netlify Function، سپس مستقیم از GitHub API) ──
  const dispatchPipeline = async (token: string): Promise<void> => {
    // ۱) بررسی Netlify Function اگر فعال باشد
    try {
      const netlifyRes = await fetch(RUN_ENDPOINT, { method: 'POST' });
      if (netlifyRes.ok) return;
    } catch {
      // سرورلس فانکشن در هاست استاتیک وجود ندارد؛ مستقیم به GitHub می‌رویم
    }

    // ۲) ارتباط مستقیم با GitHub API
    if (!token) {
      throw new Error('not_configured');
    }

    const ghRes = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token.trim()}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ref: 'main' }),
      }
    );

    if (ghRes.status === 204) {
      return;
    }
    if (ghRes.status === 401 || ghRes.status === 403) {
      throw new Error('invalid_token');
    }
    throw new Error('github_error');
  };

  // ── اجرای دستی پایپ‌لاین و بررسی تغییر دیتای خروجی ──
  const runPipeline = useCallback(async (overrideToken?: string) => {
    if (runStatus === 'starting' || runStatus === 'running') return;
    const activeToken = (overrideToken ?? githubToken).trim();

    if (!activeToken) {
      setTempTokenInput('');
      setShowTokenModal(true);
      return;
    }

    setRunStatus('starting');
    setRunMessage('در حال اتصال به GitHub…');
    try {
      // ثبت آخرین زمان دیتای فعلی
      let previousGeneratedAt = '';
      try {
        const metaRes = await fetch(`${DATA_BASE_URL}/meta.json?t=${Date.now()}`);
        if (metaRes.ok) {
          const meta = await metaRes.json();
          previousGeneratedAt = meta?.generated_at_utc ?? '';
        }
      } catch {}

      await dispatchPipeline(activeToken);

      setRunStatus('running');
      setRunMessage('پایپ‌لاین در GitHub شروع شد؛ در حال استخراج و تحلیل داده‌ها…');

      const deadline = Date.now() + 10 * 60 * 1000; // حداکثر ۱۰ دقیقه صبر
      const poll = async (): Promise<boolean> => {
        if (Date.now() > deadline) return false;
        const bust = `?t=${Date.now()}`;
        const metaRes = await fetch(`${DATA_BASE_URL}/meta.json${bust}`).catch(() => null);
        if (!metaRes || !metaRes.ok) {
          await new Promise((r) => setTimeout(r, 15_000));
          return poll();
        }
        const meta = await metaRes.json().catch(() => null);
        if (meta?.generated_at_utc && (!previousGeneratedAt || meta.generated_at_utc > previousGeneratedAt)) {
          return true;
        }
        await new Promise((r) => setTimeout(r, 15_000));
        return poll();
      };

      const done = await poll();
      if (done) {
        setRunMessage('✅ دیتای جدید منتشر شد؛ در حال بارگذاری…');
        await fetchAutoData();
        setRunStatus('ok');
        setRunMessage('✅ بروزرسانی با موفقیت انجام شد.');
        setTimeout(() => {
          setRunStatus('idle');
          setRunMessage(null);
        }, 6000);
      } else {
        setRunStatus('error');
        setRunMessage('عملیات طولانی شد؛ لطفاً بعداً دکمه «بروزرسانی» را بزنید.');
      }
    } catch (err: any) {
      setRunStatus('error');
      setRunMessage(RUN_ERROR_MESSAGES[err?.message] ?? 'اجرای پایپ‌لاین ناموفق بود.');
      if (err?.message === 'invalid_token' || err?.message === 'not_configured') {
        setTempTokenInput(activeToken);
        setShowTokenModal(true);
      }
    }
  }, [runStatus, githubToken, fetchAutoData]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target?.result as string);
        setData(json);
        setSource('manual');
        setLastUpdateIso(null);
        setAutoPaused(true);
      } catch (err) {
        alert("فرمت فایل نامعتبر است. لطفا فایل bkv_data.json خروجی اسکریپت را آپلود کنید.");
      }
    };
    reader.readAsText(file);

    // Reset file input
    e.target.value = '';
  };

  return (
    <div className="min-h-screen bg-[#050608] text-white selection:bg-emerald-500/30 font-['Vazirmatn'] flex flex-col p-4 gap-4 overflow-x-hidden">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-center bg-[#0d1117] border border-[#1f2937] p-4 rounded-xl shrink-0 gap-3">
        <div className="flex items-center gap-4">
          <div className="bg-emerald-500 w-3 h-3 rounded-full animate-pulse ml-2 md:ml-0"></div>
          <h1 className="text-xl font-bold tracking-tight text-emerald-500" dir="ltr">
            BKV <span className="text-slate-400 font-normal">| Bourse Kala View</span>
          </h1>
        </div>

        {/* وضعیت دیتا و آخرین بروزرسانی */}
        <div className="flex items-center gap-2 flex-wrap justify-center">
          {lastUpdateIso && source === 'auto' && (
            <div
              className="text-xs text-emerald-400 font-medium bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20"
              title="آخرین بروزرسانی دیتا — به وقت تهران"
            >
              آخرین بروزرسانی: {formatTehranTime(lastUpdateIso)}
            </div>
          )}
          {source === 'auto' && !lastUpdateIso && (
            <div className="text-xs text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">
              منبع: دریافت خودکار
            </div>
          )}
          {source === 'manual' && (
            <div className="text-xs text-amber-400 bg-amber-500/10 px-2 py-1 rounded border border-amber-500/20">
              منبع: آپلود دستی{autoPaused ? ' — دریافت خودکار متوقف' : ''}
            </div>
          )}
          {!dataUrlConfigured && (
            <div
              className="text-xs text-amber-400 bg-amber-500/10 px-2 py-1 rounded border border-amber-500/20"
              title="در App.tsx مقدار DATA_BASE_URL را با آدرس مخزن خود جایگزین کنید"
            >
              آدرس دیتای خودکار تنظیم نشده
            </div>
          )}
          {runMessage && (
            <div
              className={`text-xs px-2 py-1 rounded border ${
                runStatus === 'error'
                  ? 'text-rose-400 bg-rose-500/10 border-rose-500/20'
                  : 'text-blue-300 bg-blue-500/10 border-blue-500/20'
              }`}
            >
              {runMessage}
            </div>
          )}
          {dataUrlConfigured && autoStatus === 'error' && (
            <div
              className="text-xs text-rose-400 bg-rose-500/10 px-2 py-1 rounded border border-rose-500/20"
              title="می‌توانید فایل JSON را به‌صورت دستی آپلود کنید"
            >
              اتصال به دیتای خودکار ناموفق
            </div>
          )}
          <button
            onClick={() => { setAutoPaused(false); fetchAutoData(); }}
            disabled={autoStatus === 'loading' || !dataUrlConfigured}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${autoStatus === 'loading' ? 'animate-spin' : ''}`} />
            <span>{autoPaused ? 'ادامه دریافت خودکار' : 'بروزرسانی'}</span>
          </button>
        </div>

        <div className="flex items-center gap-3">
          {/* دکمه اجرای پایپ‌لاین + تنظیم توکن */}
          <div className="flex items-center rounded-lg border border-blue-500/30 bg-blue-600/20 overflow-hidden shadow-sm">
            <button
              onClick={() => runPipeline()}
              disabled={runStatus === 'starting' || runStatus === 'running'}
              className="flex items-center justify-center gap-2 px-3.5 py-2 text-sm transition-all hover:bg-blue-600/30 text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
              title="اجرای پایپ‌لاین روی GitHub Actions و دریافت دیتای تازه"
            >
              <PlayCircle className={`w-4 h-4 ${runStatus === 'running' ? 'animate-pulse' : ''}`} />
              <span>
                {runStatus === 'starting'
                  ? 'در حال ارسال…'
                  : runStatus === 'running'
                  ? 'در حال اجرا…'
                  : runStatus === 'ok'
                  ? 'انجام شد ✓'
                  : 'اجرای پایپ‌لاین'}
              </span>
            </button>
            <button
              onClick={() => {
                setTempTokenInput(githubToken);
                setShowTokenModal(true);
              }}
              className="px-2.5 py-2 hover:bg-blue-600/40 text-blue-300 border-r border-blue-500/30 transition-colors"
              title="تنظیمات توکن گیت‌هاب (PAT)"
            >
              <KeyRound className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={() => setShowScript(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700 text-sm"
          >
            <Code2 className="w-4 h-4" />
            <span>اسکریپت پایتون</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm transition-all border border-emerald-400/20"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
            <span>آپلود JSON</span>
          </button>
          <input
            type="file"
            accept=".json"
            className="hidden"
            ref={fileInputRef}
            onChange={handleFileUpload}
          />
        </div>
      </header>

      {/* Main Dashboard Area */}
      <main className="flex-1 w-full max-w-[1920px] mx-auto flex flex-col min-h-0">
        <Dashboard data={data} />
      </main>

      {/* Footer */}
      <footer className="flex justify-between items-center text-[10px] text-slate-500 uppercase tracking-widest pt-2 px-2 shrink-0 border-t border-slate-800/50 mt-auto">
        <div className="flex gap-6">
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-500"></span><span>داده‌های ریالی</span></div>
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-blue-500"></span><span>شاخص حباب</span></div>
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-500/50"></span><span>نسبت طلا</span></div>
        </div>
        <div className="font-mono" dir="ltr">SYSTEM STATUS: LATEST | V 2.4.0</div>
      </footer>

      {/* Token Settings Modal */}
      {showTokenModal && (
        <div
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setShowTokenModal(false)}
        >
          <div
            className="bg-[#0d1117] border border-blue-500/30 rounded-xl w-full max-w-md shadow-2xl p-5 flex flex-col gap-4 text-right"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-sm text-blue-400 flex items-center gap-2">
                <KeyRound className="w-4 h-4" />
                <span>تنظیم توکن اجرای مستقیم پایپ‌لاین</span>
              </h3>
              <button
                onClick={() => setShowTokenModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              برای اینکه دکمهٔ «اجرای پایپ‌لاین» بتواند مستقیماً اکشن گیت‌هاب را اجرا کند، توکن شخصی گیت‌هاب (PAT با دسترسی repo و workflow) را وارد کنید. این توکن به‌صورت امن در حافظه مرورگر شما (Local Storage) ذخیره می‌شود.
            </p>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-slate-400">توکن گیت‌هاب (PAT):</label>
              <input
                type="password"
                value={tempTokenInput}
                onChange={(e) => setTempTokenInput(e.target.value)}
                placeholder="ghp_..."
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                dir="ltr"
              />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-800">
              {githubToken ? (
                <button
                  onClick={() => {
                    setGithubToken('');
                    setTempTokenInput('');
                    localStorage.removeItem('bkv_github_token');
                  }}
                  className="text-xs text-rose-400 hover:text-rose-300"
                >
                  حذف توکن
                </button>
              ) : <div />}

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowTokenModal(false)}
                  className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:bg-slate-800 transition-colors"
                >
                  انصراف
                </button>
                <button
                  onClick={() => {
                    const val = tempTokenInput.trim();
                    setGithubToken(val);
                    localStorage.setItem('bkv_github_token', val);
                    setShowTokenModal(false);
                    if (val) {
                      setTimeout(() => runPipeline(val), 100);
                    }
                  }}
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>ذخیره و اجرا</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Script Modal */}
      {showScript && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-6" onClick={() => setShowScript(false)}>
          <div className="bg-[#0d1117] border border-slate-700 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-[#0d1117]">
              <h3 className="font-bold text-sm text-emerald-500 flex items-center gap-2 uppercase tracking-widest">
                اسکریپت بروزرسانی بورس کالا
              </h3>
              <button
                onClick={() => setShowScript(false)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 custom-scrollbar">
              <div className="bg-black/50 p-4 rounded-xl border border-white/5">
                <pre className="text-xs text-emerald-400 font-mono leading-relaxed truncate whitespace-pre-wrap" dir="ltr">
                  {PYTHON_SCRIPT}
                </pre>
              </div>
            </div>
            <div className="p-4 border-t border-slate-800 bg-[#0d1117] flex justify-between items-center">
              <p className="text-xs text-slate-400">
                این کد را در Google Colab اجرا کنید، سپس فایل دیتای خروجی را در همینجا آپلود کنید.
              </p>
              <button
                onClick={() => navigator.clipboard.writeText(PYTHON_SCRIPT)}
                className="px-4 py-2 bg-emerald-900/50 hover:bg-emerald-900 border border-emerald-500/30 rounded-lg text-xs font-semibold transition-colors text-emerald-400"
              >
                کپی کردن کد
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
