"use client";

import { GUIDA_TIKR_PATH, researchLinksForTicker } from "@/lib/externalLinks";

interface Props {
  ticker: string;
  compact?: boolean;
}

export default function ExternalResearchLinks({ ticker, compact }: Props) {
  if (!ticker || ticker === "—") return null;

  const links = researchLinksForTicker(ticker);

  return (
    <div className={`external-links${compact ? " external-links-compact" : ""}`}>
      <span className="external-links-label">Ricerca esterna</span>
      <div className="external-links-row">
        {links.map((link) => (
          <a
            key={link.id}
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            className={`external-link external-link-${link.id}`}
            title={link.hint}
            onClick={(e) => e.stopPropagation()}
          >
            {link.label}
          </a>
        ))}
        <a
          href={GUIDA_TIKR_PATH}
          target="_blank"
          rel="noopener noreferrer"
          className="external-link external-link-guide"
          title="Guida con screenshot TIKR + SEC (es. ADGM)"
          onClick={(e) => e.stopPropagation()}
        >
          Guida lettura
        </a>
      </div>
    </div>
  );
}
