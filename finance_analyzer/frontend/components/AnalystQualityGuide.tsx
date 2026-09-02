"use client";

const CRITERIA: {
  metric: string;
  better: string;
  caution: string;
  why: string;
}[] = [
  {
    metric: "N. analisti",
    better: "≥ 5 (ideale ≥ 10)",
    caution: "1–2 analisti",
    why: "Più copertura = consenso più affidabile. Con 1 solo analista lo spread può essere 0% ma il dato è debole.",
  },
  {
    metric: "Spread target",
    better: "≤ 40%",
    caution: "> 60%",
    why: "Spread = quanto discordano i target min/max. Basso = analisti d’accordo sul prezzo giusto.",
  },
  {
    metric: "Range target",
    better: "Min–max stretto e vicino al target medio",
    caution: "Range molto ampio (es. 10–45)",
    why: "Il range è in $/€ (non 1–100): indica incertezza sul valore intrinseco.",
  },
  {
    metric: "% Buy",
    better: "≥ 65%",
    caution: "< 35%",
    why: "Quota di analisti con rating Buy sul totale (Buy + Hold + Sell).",
  },
  {
    metric: "Upside",
    better: "Positivo ma realistico (+10–50%)",
    caution: "> 100% su titolo in perdita",
    why: "Upside alto non basta: verifica se gli analisti prevedono utili o solo speranza sulla pipeline.",
  },
  {
    metric: "Date target",
    better: "Ultimo target < 4 mesi",
    caution: "> 6 mesi o consenso vecchio",
    why: "Controlla «Target …» e «Consenso …» sotto % Buy. Dati datati = meno affidabili.",
  },
];

export default function AnalystQualityGuide() {
  return (
    <details className="analyst-quality-guide">
      <summary>Guida: cosa rende un titolo «più leggibile» (analisti)</summary>
      <p className="guide-intro">
        Usa le colonne <strong>Range target</strong> e <strong>Spread</strong> insieme a{" "}
        <strong>% Buy</strong>. Verde = segnale più forte, rosso = più cautela. Strumento
        educativo, non consulenza.
      </p>
      <div className="guide-table-wrap">
        <table className="guide-table">
          <thead>
            <tr>
              <th>Metrica</th>
              <th>Meglio</th>
              <th>Attenzione</th>
              <th>Perché</th>
            </tr>
          </thead>
          <tbody>
            {CRITERIA.map((row) => (
              <tr key={row.metric}>
                <td>{row.metric}</td>
                <td className="guide-good">{row.better}</td>
                <td className="guide-warn">{row.caution}</td>
                <td>{row.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="glossary-note">
        Esempio forte: 9 analisti, range 40–55 USD, spread 32%, % Buy 100%. Esempio debole: 2
        analisti, range 6–7, spread 15% ma copertura insufficiente.{" "}
        <a
          href="/guida-analisti/GUIDA_RANGE_SPREAD_ANALISTI.md"
          target="_blank"
          rel="noopener noreferrer"
          className="guide-md-link"
        >
          Guida completa (MD)
        </a>
      </p>
    </details>
  );
}
