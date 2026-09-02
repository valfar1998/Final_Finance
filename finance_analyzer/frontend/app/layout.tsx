import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finance Analyzer — Analisi ETF, Azioni, Obbligazioni",
  description:
    "Analisi storica da Stooq, metriche di rendimento e simulazioni probabilistiche. Non è consulenza finanziaria.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
