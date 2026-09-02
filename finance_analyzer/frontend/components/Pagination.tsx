"use client";

interface Props {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

export default function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: Props) {
  const pages = buildPageList(page, totalPages);

  return (
    <div className="pagination">
      <div className="pagination-info">
        Pagina <strong>{page}</strong> di <strong>{totalPages.toLocaleString("it-IT")}</strong>
        {" · "}
        <strong>{total.toLocaleString("it-IT")}</strong> azioni totali
      </div>

      <div className="pagination-controls">
        <button type="button" disabled={page <= 1} onClick={() => onPageChange(1)}>
          ««
        </button>
        <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          ‹
        </button>

        {pages.map((p, i) =>
          p === "…" ? (
            <span key={`ellipsis-${i}`} className="page-ellipsis">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              className={p === page ? "active" : ""}
              onClick={() => onPageChange(p as number)}
            >
              {p}
            </button>
          ),
        )}

        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          ›
        </button>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(totalPages)}
        >
          »»
        </button>
      </div>

      <label className="pagination-size">
        <span>Righe</span>
        <select value={pageSize} onChange={(e) => onPageSizeChange(Number(e.target.value))}>
          <option value={25}>25</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
      </label>
    </div>
  );
}

function buildPageList(current: number, total: number): (number | "…")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const list: (number | "…")[] = [1];
  if (current > 3) list.push("…");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
    list.push(p);
  }
  if (current < total - 2) list.push("…");
  list.push(total);
  return list;
}
