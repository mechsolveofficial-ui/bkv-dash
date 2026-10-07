export interface DataPoint {
  date: string;
  ime_price: number;
  global_rial: number;
  bubble_pct: number;
  global_usd: number;
  gold_ratio: number;
}

export interface HorizonData {
  days: number;
  avg_return_pct: number | null;
  median_return_pct?: number | null;
  sample_count?: number;
}

export interface BinForecast {
  avg_first_peak_return_pct: number | null;
  avg_days_to_first_peak: number | null;
  avg_first_trough_return_pct: number | null;
  avg_days_to_first_trough: number | null;
  matched_points: number;
  peak_samples: number;
  trough_samples: number;
  horizons?: Record<string, HorizonData>;
}

export type CommodityDataset = DataPoint[] | { 
  main: DataPoint[], 
  historical: DataPoint[],
  bubble_analysis?: {
    Q: string;
    x: number;
  },
  bin_forecast?: BinForecast;
};
export type BkvData = Record<string, CommodityDataset>;

export const COMMODITIES_INFO = [
  { id: 'gold_995', name: 'طلای ۲۴ عیار', unit: 'گرم', color: '#fbbf24' },
  { id: 'gold_coin', name: 'سکه طلا', unit: 'قطعه', color: '#f59e0b' },
  { id: 'silver', name: 'نقره', unit: 'گرم', color: '#cbd5e1' },
  { id: 'copper', name: 'مس', unit: 'کیلوگرم', color: '#c2410c' },
  { id: 'zinc', name: 'روی', unit: 'کیلوگرم', color: '#94a3b8' },
  { id: 'iron', name: 'سنگ آهن', unit: 'کیلوگرم', color: '#7f1d1d' },
  { id: 'bitumen', name: 'قیر', unit: 'کیلوگرم', color: '#1e293b' },
];
