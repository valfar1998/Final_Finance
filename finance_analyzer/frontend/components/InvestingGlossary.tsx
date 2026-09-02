"use client";

const GLOSSARY: { term: string; def: string }[] = [
  { term: "Target / Range", def: "Prezzo obiettivo analisti (min–max in $/€)." },
  { term: "Upside", def: "(Target − prezzo) / prezzo. Potenziale rialzo, non garanzia." },
  { term: "% Buy", def: "Analisti con rating Buy ÷ totale × 100." },
  { term: "Spread", def: "Quanto discordano i target ( stretto = consenso )." },
  { term: "10-K / 10-Q", def: "Bilancio annuale / trimestrale SEC (dati ufficiali)." },
  { term: "8-K", def: "Evento urgente (FDA, Nasdaq, CEO, offerta azioni)." },
  { term: "LTM / NTM", def: "Ultimi 12 mesi / Prossimi 12 mesi." },
  { term: "EV / Market Cap", def: "Valore impresa (con debito) / solo azioni." },
  { term: "Diluizione", def: "Nuove azioni emesse → la tua quota vale meno." },
];

export default function InvestingGlossary() {
  return (
    <details className="investing-glossary" open>
      <summary>Mini-glossario (TIKR / SEC / analisti)</summary>
      <dl className="glossary-list">
        {GLOSSARY.map(({ term, def }) => (
          <div key={term} className="glossary-item">
            <dt>{term}</dt>
            <dd>{def}</dd>
          </div>
        ))}
      </dl>
      <p className="glossary-note">
        Strumento educativo — verifica sempre date e documenti SEC prima di decidere.
      </p>
    </details>
  );
}
