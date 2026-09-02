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
import type { ChartPoint } from "@/lib/api";

interface Props {
  data: ChartPoint[];
  title: string;
  color?: string;
}

export default function PriceChart({ data, title, color = "#3b82f6" }: Props) {
  if (!data.length) {
    return <div className="chart-empty">Nessun dato disponibile per il grafico.</div>;
  }

  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(0, 7),
  }));

  return (
    <div className="chart-card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={formatted} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => String(v).slice(0, 7)}
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            domain={["auto", "auto"]}
            tickFormatter={(v) => Number(v).toFixed(0)}
          />
          <Tooltip
            contentStyle={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              color: "#f1f5f9",
            }}
            labelFormatter={(l) => `Data: ${l}`}
            formatter={(value: number) => [value.toFixed(2), "Prezzo"]}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="close"
            name="Prezzo di chiusura (Stooq)"
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
