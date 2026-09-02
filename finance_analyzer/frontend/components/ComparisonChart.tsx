"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { AssetRow } from "@/lib/api";

const COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#ef4444", "#06b6d4", "#ec4899", "#84cc16"];

interface Props {
  assets: AssetRow[];
  title?: string;
}

function buildNormalizedSeries(assets: AssetRow[]) {
  const dateMap = new Map<string, Record<string, number>>();

  assets.forEach((asset) => {
    const chart = asset.chart;
    if (!chart.length) return;
    const base = chart[0].close;
    if (!base) return;
    chart.forEach((pt) => {
      const row = dateMap.get(pt.date) ?? {};
      row[asset.id] = Math.round((pt.close / base) * 1000) / 10;
      dateMap.set(pt.date, row);
    });
  });

  return Array.from(dateMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, values]) => ({ date, ...values }));
}

export default function ComparisonChart({ assets, title }: Props) {
  const data = buildNormalizedSeries(assets);
  const withData = assets.filter((a) => a.chart.length > 0);

  if (!data.length || !withData.length) {
    return null;
  }

  return (
    <div className="chart-card">
      <h3>{title ?? "Confronto performance normalizzata (base 100)"}</h3>
      <p className="chart-subtitle">
        Filtrato per regione/tipo selezionati. Base 100 all&apos;inizio dello storico.
      </p>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => String(v).slice(0, 7)}
            minTickGap={50}
          />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              color: "#f1f5f9",
            }}
            labelFormatter={(l) => `Data: ${l}`}
            formatter={(value: number, name: string) => {
              const asset = withData.find((a) => a.id === name);
              return [`${value}`, asset?.name ?? name];
            }}
          />
          <Legend />
          {withData.map((a, i) => (
            <Line
              key={a.id}
              type="monotone"
              dataKey={a.id}
              name={a.name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
