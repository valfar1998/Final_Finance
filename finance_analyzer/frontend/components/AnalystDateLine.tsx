"use client";

import { fmtAnalystDates, analystDateIsStale } from "@/lib/format";

interface Props {
  consensusDate?: string | null;
  lastTargetDate?: string | null;
  lastRatingDate?: string | null;
  lastFirm?: string | null;
  className?: string;
}

export default function AnalystDateLine({
  consensusDate,
  lastTargetDate,
  lastRatingDate,
  lastFirm,
  className = "analyst-date",
}: Props) {
  const text = fmtAnalystDates({
    analyst_consensus_date: consensusDate,
    analyst_last_target_date: lastTargetDate,
    analyst_last_rating_date: lastRatingDate,
    analyst_last_firm: lastFirm,
  });
  if (!text) return null;

  const stale = analystDateIsStale(lastTargetDate ?? lastRatingDate ?? consensusDate);

  return (
    <span className={`${className}${stale ? " analyst-date-stale" : ""}`} title={text}>
      📅 {text}
      {stale ? " · dati non recenti" : ""}
    </span>
  );
}
