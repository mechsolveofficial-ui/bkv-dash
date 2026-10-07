import React, { useState } from 'react';
import { BkvData, COMMODITIES_INFO } from '../types';
import { AlertCircle, TrendingDown, TrendingUp } from 'lucide-react';

interface Props {
  data: BkvData | null;
}

export function DecisionPanel({ data }: Props) {
  const [activeTab, setActiveTab] = useState<'status' | 'forecast' | 'horizons'>('status');

  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="bg-emerald-900/10 border-2 border-emerald-500/30 rounded-xl p-4 flex flex-col h-[420px]">
        <div className="flex items-center gap-2 mb-3">
          <div className="bg-emerald-500/20 p-1.5 rounded-lg">
            <AlertCircle className="w-5 h-5 text-emerald-500" />
          </div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Decision Hub</h3>
        </div>
        <div className="flex-1 flex items-center justify-center border border-white/5 rounded-xl bg-black/40 mt-2">
          <p className="text-slate-500 text-xs text-center px-4">
            Import JSON to refresh AI metrics and asset signals based on latest Python computation.
          </p>
        </div>
      </div>
    );
  }

  // Get the latest date from the data
  let latestDateStr = '';
  const firstCommodity = COMMODITIES_INFO.length > 0 ? COMMODITIES_INFO[0] : null;
  if (firstCommodity && data && data[firstCommodity.id]) {
    const rawSeries = data[firstCommodity.id];
    const series = Array.isArray(rawSeries) ? rawSeries : rawSeries.main;
    if (series && series.length > 0) {
      latestDateStr = series[series.length - 1].date;
    }
  }

  // The date from the Python script is already in Shamsi format (e.g., "1402/05/24")
  let shamsiDate = latestDateStr ? latestDateStr : '';

  // Calculate some basic decision logic
  const bubbles = COMMODITIES_INFO.map(info => {
    const rawSeries = data[info.id];
    if (!rawSeries) return null;
    const series = Array.isArray(rawSeries) ? rawSeries : rawSeries.main;
    if (!series || series.length === 0) return null;
    const latest = series[series.length - 1];

    const analysis = !Array.isArray(rawSeries) && rawSeries.bubble_analysis 
      ? rawSeries.bubble_analysis 
      : { Q: '-', x: 0 };
      
    const forecast = !Array.isArray(rawSeries) && rawSeries.bin_forecast
      ? rawSeries.bin_forecast
      : null;

    return {
      name: info.name,
      bubble: latest.bubble_pct,
      color: info.color,
      q: analysis.Q,
      x: analysis.x,
      forecast: forecast
    };
  }).filter(Boolean) as any[];

  return (
    <div className="bg-emerald-900/10 border-2 border-emerald-500/30 rounded-xl p-4 flex flex-col h-[420px]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="bg-emerald-500/20 p-1.5 rounded-lg">
            <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z"/></svg>
          </div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Decision Hub</h3>
        </div>
        {shamsiDate && (
          <div className="text-xs text-emerald-400 font-mono bg-emerald-500/10 px-2 py-1 rounded">
            {shamsiDate}
          </div>
        )}
      </div>
      
      <div className="flex gap-2 mb-3 border-b border-white/10 pb-2">
        <button 
          onClick={() => setActiveTab('status')}
          className={`text-xs px-3 py-1.5 rounded transition-colors ${activeTab === 'status' ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}
        >
          وضعیت حباب
        </button>
        <button 
          onClick={() => setActiveTab('forecast')}
          className={`text-xs px-3 py-1.5 rounded transition-colors ${activeTab === 'forecast' ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}
        >
          تحلیل تاریخچه بازه
        </button>
        <button 
          onClick={() => setActiveTab('horizons')}
          className={`text-xs px-3 py-1.5 rounded transition-colors ${activeTab === 'horizons' ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}
        >
          افق زمانی قیمت
        </button>
      </div>

      <div className="flex-1 overflow-y-auto pr-1 custom-scrollbar">
        {activeTab === 'status' && (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase border-b border-white/10">
                <th className="pb-2 font-medium">نماد</th>
                <th className="pb-2 font-medium text-center">حباب فعلی</th>
                <th className="pb-2 font-medium text-center">وضعیت (Q)</th>
                <th className="pb-2 font-medium text-center">فاصله (X)</th>
              </tr>
            </thead>
            <tbody>
              {bubbles.map((item) => (
                <tr key={item.name} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="text-xs text-slate-200">{item.name}</span>
                    </div>
                  </td>
                  <td className="py-3 text-center font-mono text-xs" dir="ltr">
                    <span className={item.bubble > 0 ? 'text-rose-400' : 'text-emerald-400'}>
                      {item.bubble > 0 ? '+' : ''}{item.bubble.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-300">
                    <span className="bg-slate-800/80 px-2 py-1 rounded text-[10px]">{item.q}</span>
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-300">
                    {item.x.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {activeTab === 'forecast' && (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase border-b border-white/10">
                <th className="pb-2 font-medium">نماد</th>
                <th className="pb-2 font-medium text-center" title="تعداد کل موارد مشابه در تاریخچه">مشابه</th>
                <th className="pb-2 font-medium text-center">سود بعدی</th>
                <th className="pb-2 font-medium text-center" title="تعداد نمونه‌های سود">#سود</th>
                <th className="pb-2 font-medium text-center">روز تا سود</th>
                <th className="pb-2 font-medium text-center">ضرر بعدی</th>
                <th className="pb-2 font-medium text-center" title="تعداد نمونه‌های ضرر">#ضرر</th>
                <th className="pb-2 font-medium text-center">روز تا ضرر</th>
              </tr>
            </thead>
            <tbody>
              {bubbles.map((item) => (
                <tr key={item.name} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="text-xs text-slate-200">{item.name}</span>
                    </div>
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-400">
                    {item.forecast?.matched_points ?? '-'}
                  </td>
                  <td className="py-3 text-center font-mono text-xs" dir="ltr">
                    <span className={item.forecast?.avg_first_peak_return_pct != null ? 'text-emerald-400' : 'text-slate-500'}>
                      {item.forecast?.avg_first_peak_return_pct != null ? '+' + item.forecast.avg_first_peak_return_pct.toFixed(2) + '%' : '-'}
                    </span>
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-400">
                    {item.forecast?.peak_samples ?? '-'}
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-300">
                    {item.forecast?.avg_days_to_first_peak != null ? item.forecast.avg_days_to_first_peak.toFixed(1) : '-'}
                  </td>
                  <td className="py-3 text-center font-mono text-xs" dir="ltr">
                    <span className={item.forecast?.avg_first_trough_return_pct != null ? 'text-rose-400' : 'text-slate-500'}>
                      {item.forecast?.avg_first_trough_return_pct != null ? item.forecast.avg_first_trough_return_pct.toFixed(2) + '%' : '-'}
                    </span>
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-400">
                    {item.forecast?.trough_samples ?? '-'}
                  </td>
                  <td className="py-3 text-center font-mono text-xs text-slate-300">
                    {item.forecast?.avg_days_to_first_trough != null ? item.forecast.avg_days_to_first_trough.toFixed(1) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {activeTab === 'horizons' && (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase border-b border-white/10">
                <th className="pb-2 font-medium">نماد</th>
                <th className="pb-2 font-medium text-center">۱ روز بعد</th>
                <th className="pb-2 font-medium text-center">۱ هفته بعد</th>
                <th className="pb-2 font-medium text-center">۱ ماه بعد</th>
                <th className="pb-2 font-medium text-center">۳ ماه بعد</th>
              </tr>
            </thead>
            <tbody>
              {bubbles.map((item) => {
                const hz = item.forecast?.horizons;
                const renderHorizon = (hKey: string) => {
                  const data = hz?.[hKey];
                  const val = data?.avg_return_pct;
                  if (val == null) return <span className="text-slate-500">-</span>;
                  const isPositive = val > 0;
                  const isZero = val === 0;
                  return (
                    <span 
                      className={isPositive ? 'text-emerald-400' : isZero ? 'text-slate-300' : 'text-rose-400'}
                      title={data.sample_count != null ? `تعداد نمونه: ${data.sample_count}` : undefined}
                    >
                      {isPositive ? '+' : ''}{val.toFixed(2)}%
                    </span>
                  );
                };

                return (
                  <tr key={item.name} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                        <span className="text-xs text-slate-200">{item.name}</span>
                      </div>
                    </td>
                    <td className="py-3 text-center font-mono text-xs" dir="ltr">
                      {renderHorizon('1d')}
                    </td>
                    <td className="py-3 text-center font-mono text-xs" dir="ltr">
                      {renderHorizon('1w')}
                    </td>
                    <td className="py-3 text-center font-mono text-xs" dir="ltr">
                      {renderHorizon('1m')}
                    </td>
                    <td className="py-3 text-center font-mono text-xs" dir="ltr">
                      {renderHorizon('3m')}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
