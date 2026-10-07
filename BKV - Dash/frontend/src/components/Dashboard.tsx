import React from 'react';
import { BkvData, COMMODITIES_INFO } from '../types';
import { CommodityWidget } from './CommodityWidget';
import { DecisionPanel } from './DecisionPanel';

interface Props {
  data: BkvData | null;
}

export function Dashboard({ data }: Props) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-6 gap-4 flex-1">
      {/* 
        ردیف اول: جایگاه تصمیم‌گیری و طلای ۹۹۵
        ردیف دوم و سوم: ۳ کادر برای هر کدام
      */}
      <div className="lg:col-span-3">
        <DecisionPanel data={data} />
      </div>

      {COMMODITIES_INFO.map((info, idx) => (
        <div key={info.id} className={idx === 0 ? "lg:col-span-3" : "lg:col-span-2"}>
          <CommodityWidget
            title={info.name}
            color={info.color}
            data={data ? data[info.id] : []}
          />
        </div>
      ))}
    </div>
  );
}
