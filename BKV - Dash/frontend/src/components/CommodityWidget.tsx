import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { Maximize2, Minimize2 } from 'lucide-react';
import { DataPoint, CommodityDataset } from '../types';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface Props {
  title: string;
  data: CommodityDataset | undefined;
  color: string;
}

export function CommodityWidget({ title, data, color }: Props) {
  const [viewMode, setViewMode] = useState<'rial' | 'usd' | 'gold_ratio'>('rial');
  const [timeframe, setTimeframe] = useState<'1M' | '3M' | '1Y' | 'ALL'>('ALL');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isBubbleFocused, setIsBubbleFocused] = useState(false);

  const parsedData = useMemo(() => {
    if (!data) return { main: [], historical: [] };
    if (Array.isArray(data)) return { main: data, historical: data };
    return data;
  }, [data]);

  const mainData = parsedData.main;
  const historicalData = parsedData.historical;

  const filteredData = useMemo(() => {
    if (!mainData || mainData.length === 0) return [];
    
    // For USD and Gold Ratio, 'ALL' means TradingView historical data
    if ((viewMode === 'usd' || viewMode === 'gold_ratio') && timeframe === 'ALL') {
      return historicalData;
    }

    if (timeframe === 'ALL') return mainData; // Rial mode ALL or fallback

    const latestDate = new Date(mainData[mainData.length - 1].date);
    let cutoffDate = new Date(latestDate);
    
    if (timeframe === '1M') cutoffDate.setMonth(cutoffDate.getMonth() - 1);
    else if (timeframe === '3M') cutoffDate.setMonth(cutoffDate.getMonth() - 3);
    else if (timeframe === '1Y') cutoffDate.setFullYear(cutoffDate.getFullYear() - 1);
    
    return mainData.filter(d => new Date(d.date) >= cutoffDate);
  }, [mainData, historicalData, timeframe, viewMode]);

  const enhancedData = useMemo(() => {
    return filteredData.map(item => {
      const isImeHigher = item.ime_price > item.global_rial;
      return {
        ...item,
        pos_range: isImeHigher ? [item.global_rial, item.ime_price] : null,
        neg_range: !isImeHigher ? [item.ime_price, item.global_rial] : null,
      };
    });
  }, [filteredData]);

  const xTicks = useMemo(() => {
    if (timeframe !== 'ALL' || viewMode === 'rial') return undefined; // only for historical 10-year
    const ticks: string[] = [];
    let currentYear = '';
    for (const d of enhancedData) {
      const year = d.date.substring(0, 4);
      if (year !== currentYear) {
        ticks.push(d.date);
        currentYear = year;
      }
    }
    return ticks;
  }, [enhancedData, timeframe, viewMode]);

  if (!mainData || mainData.length === 0) {
    return (
      <div className="bg-[#0d1117] border border-slate-800 rounded-xl p-4 flex flex-col h-[400px]">
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color }}>{title}</span>
        </div>
        <div className="flex-1 bg-white rounded flex items-center justify-center border border-slate-300 relative overflow-hidden mb-3">
          <span className="text-slate-400 text-sm font-sans font-medium">NO DATA</span>
        </div>
      </div>
    );
  }

  const cn = (...inputs: string[]) => twMerge(clsx(inputs));

  // Determine latest values for summary ALWAYS from mainData
  const latest = mainData[mainData.length - 1];
  const prevImePrice = mainData.length > 1 ? mainData[mainData.length - 2].ime_price : null;
  const imePriceDiff = prevImePrice !== null ? latest.ime_price - prevImePrice : null;
  const imeDiffPercent = prevImePrice ? ((latest.ime_price - prevImePrice) / prevImePrice) * 100 : null;

  const gradientOffset = () => {
    if (filteredData.length === 0) return 0;
    const dataMax = Math.max(...filteredData.map(i => i.bubble_pct));
    const dataMin = Math.min(...filteredData.map(i => i.bubble_pct));
    if (dataMax <= 0) return 0;
    if (dataMin >= 0) return 1;
    return dataMax / (dataMax - dataMin);
  };

  const off = gradientOffset();

  const maxIme = mainData.length > 0 ? Math.max(...mainData.map(d => d.ime_price)) : 0;
  const irUnitText = maxIme >= 1000000 ? 'میلیون ریال' : maxIme >= 1000 ? 'هزار ریال' : 'ریال';

  const yAxisFormatter = (val: number) => {
    if (maxIme >= 1000000) return Math.floor(val / 1000000).toString();
    if (maxIme >= 1000) return Math.floor(val / 1000).toString();
    return val.toLocaleString();
  };

  const usdFormatter = (val: number) => Math.round(val).toLocaleString();

  const xAxisFormatter = (val: string) => {
    if (!val) return '';
    // Only format as year if it's the TradingView 10-year chart
    if (timeframe === 'ALL' && viewMode !== 'rial') {
      return val.substring(0, 4);
    }
    return val;
  };

  const widgetContent = (
    <>
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color }}>{title}</span>
          <button 
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="text-slate-400 hover:text-white transition-colors p-1 rounded hover:bg-slate-800"
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
        <div className="text-left" dir="ltr">
          {viewMode === 'rial' && (
            <div className="flex flex-col items-end">
              <span className="text-sm font-semibold text-slate-300">
                {latest.ime_price.toLocaleString()} IRR
              </span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={cn("text-xs font-bold", latest.bubble_pct >= 0 ? "text-rose-400" : "text-emerald-400")}>
                  حباب: {latest.bubble_pct > 0 ? '+' : ''}{latest.bubble_pct.toFixed(1)}%
                </span>
                {imePriceDiff !== null && imeDiffPercent !== null && (
                  <span
                    className={cn(
                      "text-xs font-mono font-medium",
                      imeDiffPercent > 0 ? "text-emerald-400" : imeDiffPercent < 0 ? "text-rose-400" : "text-slate-400"
                    )}
                    title={`تغییر نسبت به روز کاری قبل: ${imePriceDiff > 0 ? '+' : ''}${imePriceDiff.toLocaleString()} IRR (${imeDiffPercent > 0 ? '+' : ''}${imeDiffPercent.toFixed(2)}%)`}
                  >
                    ({imeDiffPercent > 0 ? '+' : ''}{imeDiffPercent.toFixed(2)}%)
                  </span>
                )}
              </div>
            </div>
          )}
          {viewMode === 'usd' && (
            <span className="text-sm font-semibold text-emerald-400">
              ${latest.global_usd.toLocaleString()}
            </span>
          )}
          {viewMode === 'gold_ratio' && (
            <span className="text-sm font-semibold text-amber-400">
              {latest.gold_ratio.toFixed(4)} oz
            </span>
          )}
        </div>
      </div>

      {/* Chart Area */}
      <div className="flex-1 bg-white rounded flex flex-col relative overflow-hidden mb-3 p-1 shrink-0 h-0 text-black border border-slate-300" dir="ltr">
        {viewMode === 'rial' ? (
          <div className="flex flex-col w-full h-full">
            {/* Top Chart: Price Analysis */}
            {(!isFullscreen || !isBubbleFocused) && (
            <div className={cn("min-h-0 w-full relative pt-2", isFullscreen && !isBubbleFocused ? "flex-[2]" : "flex-[2]")}>
              <h4 className="text-center text-sm text-black mb-1 font-sans font-medium">
                Price Analysis: {title} - IME vs Global
              </h4>
              <div className="absolute top-2 left-1 text-[9px] font-bold text-slate-500 z-10 font-['Vazirmatn']" dir="rtl">
                ({irUnitText})
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={enhancedData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={true} />
                  <XAxis dataKey="date" hide />
                  <YAxis stroke="#000" fontSize={10} width={40} tickFormatter={yAxisFormatter} tick={{fill: 'black'}} />
                  <Tooltip
                    labelFormatter={(label) => `تاریخ: ${label}`}
                    formatter={(value: any) => {
                      if (Array.isArray(value)) {
                        return Number(Math.abs(value[1] - value[0])).toLocaleString();
                      }
                      return Number(value).toLocaleString();
                    }}
                    contentStyle={{ backgroundColor: 'white', borderColor: '#ccc', borderRadius: '4px', fontSize: '11px', color: 'black' }}
                    itemStyle={{ color: 'black' }}
                  />
                  <Legend 
                     verticalAlign="top" 
                     align="left"
                     iconType="plainline"
                     wrapperStyle={{ fontSize: '11px', paddingBottom: '10px', paddingTop: '5px' }} 
                  />
                  <Area type="monotone" dataKey="pos_range" fill="#2ca02c" fillOpacity={0.2} stroke="none" name="Positive Bubble" isAnimationActive={false} />
                  <Area type="monotone" dataKey="neg_range" fill="#d62728" fillOpacity={0.2} stroke="none" name="Negative Bubble" isAnimationActive={false} />
                  <Line type="monotone" dataKey="ime_price" stroke="#1f77b4" strokeWidth={2} name={`${title} IME (Rial)`} dot={false} activeDot={{r: 4}} isAnimationActive={false}/>
                  <Line type="monotone" dataKey="global_rial" stroke="#d62728" strokeWidth={2} strokeDasharray="5 5" name={`Global ${title} (Rial Equiv.)`} dot={false} activeDot={{r: 4}} isAnimationActive={false}/>
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            )}
            {/* Bottom Chart: Bubble Trend */}
            <div className={cn("min-h-0 w-full relative pt-4", (!isFullscreen || !isBubbleFocused) ? "flex-1" : "flex-1 h-full")}>
              {isFullscreen && (
                <button 
                  onClick={() => setIsBubbleFocused(!isBubbleFocused)}
                  className="absolute top-1 right-1 z-10 text-slate-400 hover:text-black transition-colors p-1"
                  title="بزرگنمایی نمودار حباب"
                >
                  {isBubbleFocused ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
                </button>
              )}
              <h4 className="text-center text-[12px] text-black mb-1 font-sans font-medium">
                {title} Bubble Percentage Trend
              </h4>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={enhancedData} margin={{ top: 5, right: 10, left: 0, bottom: 45 }}>
                  <defs>
                    <linearGradient id={`splitColor-${title.replace(/\s+/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset={off} stopColor="#2ca02c" stopOpacity={0.3} />
                      <stop offset={off} stopColor="#d62728" stopOpacity={0.3} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={true} />
                  <XAxis dataKey="date" stroke="#000" fontSize={9} minTickGap={(timeframe === 'ALL' && viewMode !== 'rial') ? 0 : 30} ticks={xTicks} tickFormatter={xAxisFormatter} tick={{fill: 'black'}} angle={-35} textAnchor="end" dy={10} />
                  <YAxis stroke="#000" fontSize={11} width={50} tickFormatter={(val) => `${val}`} tick={{fill: 'black'}} />
                  <Tooltip
                    labelFormatter={(label) => `تاریخ: ${label}`}
                    formatter={(value: any) => Number(value).toFixed(2) + '%'}
                    contentStyle={{ backgroundColor: 'white', borderColor: '#ccc', borderRadius: '4px', fontSize: '11px', color: 'black' }}
                  />
                  <ReferenceLine y={0} stroke="#0000ff" strokeWidth={1.5} />
                  <Area type="monotone" dataKey="bubble_pct" stroke="#000000" strokeWidth={1.2} fill={`url(#splitColor-${title.replace(/\s+/g, '')})`} name="Percentage (%)" dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : viewMode === 'usd' ? (
          <div className="flex flex-col w-full h-full pt-4">
            <h4 className="text-center text-sm text-black mb-2 font-sans font-medium">
              Price Analysis: {title} (USD)
            </h4>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={enhancedData} margin={{ top: 10, right: 10, left: 5, bottom: 45 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={true} />
                <XAxis dataKey="date" stroke="#000" fontSize={9} minTickGap={(timeframe === 'ALL' && viewMode !== 'rial') ? 0 : 30} ticks={xTicks} tickFormatter={xAxisFormatter} tick={{fill: 'black'}} angle={-35} textAnchor="end" dy={10} />
                <YAxis stroke="#000" fontSize={10} width={45} domain={['auto', 'auto']} tickFormatter={usdFormatter} tick={{fill: 'black'}} />
                <Tooltip
                  labelFormatter={(label) => `تاریخ: ${label}`}
                  formatter={(value: any) => '$' + Number(value).toLocaleString()}
                  contentStyle={{ backgroundColor: 'white', borderColor: '#ccc', borderRadius: '4px', fontSize: '12px', color: 'black' }}
                  itemStyle={{ color: 'black' }}
                />
                <Line type="monotone" dataKey="global_usd" stroke="#1f77b4" strokeWidth={2} name={`${title} (USD)`} dot={false} isAnimationActive={false}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex flex-col w-full h-full pt-4">
            <h4 className="text-center text-sm text-black mb-2 font-sans font-medium">
              Price Analysis: {title} / Gold Ratio
            </h4>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={enhancedData} margin={{ top: 10, right: 10, left: 5, bottom: 45 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={true} />
                <XAxis dataKey="date" stroke="#000" fontSize={9} minTickGap={(timeframe === 'ALL' && viewMode !== 'rial') ? 0 : 30} ticks={xTicks} tickFormatter={xAxisFormatter} tick={{fill: 'black'}} angle={-35} textAnchor="end" dy={10} />
                <YAxis stroke="#000" fontSize={10} width={45} domain={['auto', 'auto']} tickFormatter={(v) => v.toFixed(3)} tick={{fill: 'black'}} />
                <Tooltip
                  labelFormatter={(label) => `تاریخ: ${label}`}
                  formatter={(value: any) => Number(value).toFixed(4) + ' oz'}
                  contentStyle={{ backgroundColor: 'white', borderColor: '#ccc', borderRadius: '4px', fontSize: '12px', color: 'black' }}
                  itemStyle={{ color: 'black' }}
                />
                <Line type="monotone" dataKey="gold_ratio" stroke="#1f77b4" strokeWidth={2} name="Gold Ratio (oz)" dot={false} isAnimationActive={false}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Constraints & Filters */}
      <div className="mt-auto shrink-0 flex flex-col gap-2">
        {viewMode !== 'rial' && (
          <div className="grid grid-cols-4 gap-1">
            {(['1M', '3M', '1Y', 'ALL'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  "text-[9px] py-1 rounded border border-slate-700 transition-colors uppercase font-sans",
                  timeframe === tf 
                    ? "bg-slate-700 text-white" 
                    : "bg-slate-800/50 text-slate-400 hover:bg-slate-700"
                )}
              >
                {tf === 'ALL' ? 'HISTORICAL' : tf}
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={() => { setViewMode('rial'); setTimeframe('ALL'); }}
            className={cn(
              "text-[10px] py-1.5 rounded border border-slate-700 transition-colors uppercase font-sans shadow-sm",
              viewMode === 'rial' 
                ? "bg-slate-700 text-white" 
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            )}
          >
            Rial
          </button>
          <button
            onClick={() => setViewMode('usd')}
            className={cn(
              "text-[10px] py-1.5 rounded border border-slate-700 transition-colors uppercase font-sans shadow-sm",
              viewMode === 'usd' 
                ? "bg-slate-700 text-emerald-400" 
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            )}
          >
            GLOBAL (USD)
          </button>
          <button
            onClick={() => setViewMode('gold_ratio')}
            className={cn(
              "text-[10px] py-1.5 rounded border border-slate-700 transition-colors uppercase font-sans shadow-sm",
              viewMode === 'gold_ratio' 
                ? "bg-slate-700 text-amber-500" 
                : "bg-slate-800 text-amber-500/70 hover:bg-slate-700 hover:text-amber-500"
            )}
          >
            GOLD RATIO
          </button>
        </div>
      </div>
    </>
  );

  if (isFullscreen) {
    return createPortal(
      <div className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-sm p-4 md:p-8 flex items-center justify-center pointer-events-auto overflow-y-auto">
        <div className="bg-[#0d1117] border border-slate-700 rounded-xl p-6 flex flex-col shadow-2xl w-full max-w-6xl h-full md:h-[90vh]">
           {widgetContent}
        </div>
      </div>,
      document.body
    );
  }

  return (
    <div className="bg-[#0d1117] border border-slate-800 rounded-xl p-4 flex flex-col h-[420px]">
      {widgetContent}
    </div>
  );
}
