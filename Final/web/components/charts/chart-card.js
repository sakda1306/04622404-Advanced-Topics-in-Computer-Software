"use client";

import { useId, useState } from "react";
import { BarChart3, Table2 } from "lucide-react";

/**
 * Card around every chart: title, short explanation, the chart, and a
 * "แสดงเป็นตาราง" switch so the numbers are never only in the picture
 * (DesignSystem.md 6: status never shown by colour alone; a table view exists).
 */
export function ChartCard({ title, description, table, legend, note, children, className = "" }) {
  const [asTable, setAsTable] = useState(false);
  const titleId = useId();

  return (
    <section
      aria-labelledby={titleId}
      className={`flex flex-col rounded-lg border border-border bg-glass p-5 ${className}`}
    >
      <header className="flex items-start gap-3">
        <div className="flex-1">
          <h3 id={titleId} className="text-h3 font-semibold text-text">
            {title}
          </h3>
          {description && <p className="mt-1 text-small text-text-muted">{description}</p>}
        </div>
        {table && (
          <button
            type="button"
            onClick={() => setAsTable((v) => !v)}
            aria-pressed={asTable}
            className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md px-3 text-small text-text-muted hover:bg-bg hover:text-text"
          >
            {asTable ? (
              <BarChart3 className="size-4" strokeWidth={1.5} aria-hidden="true" />
            ) : (
              <Table2 className="size-4" strokeWidth={1.5} aria-hidden="true" />
            )}
            {asTable ? "แสดงเป็นกราฟ" : "แสดงเป็นตาราง"}
          </button>
        )}
      </header>

      {legend && !asTable && <div className="mt-3">{legend}</div>}

      <div className="mt-4 flex-1">{asTable && table ? <DataTable {...table} /> : children}</div>

      {note && <p className="mt-4 text-tiny text-text-muted">{note}</p>}
    </section>
  );
}

function DataTable({ columns, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-small">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th
                key={c}
                scope="col"
                className={`border-b border-border py-2 pr-4 font-medium text-text-muted ${i ? "text-right" : "text-left"}`}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td
                  key={i}
                  className={`tabular border-b border-border py-2 pr-4 text-text ${i ? "text-right" : "text-left"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Legend item: a short line (solid or dashed) in the series colour, then text in text colour. */
export function LegendItem({ color, dashed = false, children }) {
  return (
    <span className="inline-flex items-center gap-2 text-small text-text">
      <svg width="22" height="10" aria-hidden="true">
        <line
          x1="1"
          y1="5"
          x2="21"
          y2="5"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={dashed ? "4 4" : undefined}
        />
      </svg>
      {children}
    </span>
  );
}

/** Tooltip box shared by the Recharts charts. */
export function TooltipBox({ title, rows }) {
  return (
    <div className="rounded-md border border-border bg-bg px-3 py-2 text-small shadow-md">
      {title && <p className="font-semibold text-text">{title}</p>}
      <ul className="mt-1 space-y-0.5">
        {rows.map(({ color, dashed, label, value }) => (
          <li key={label} className="flex items-center gap-2 text-text-muted">
            {color && (
              <svg width="14" height="8" aria-hidden="true">
                <line x1="1" y1="4" x2="13" y2="4" stroke={color} strokeWidth="2.5" strokeDasharray={dashed ? "3 3" : undefined} />
              </svg>
            )}
            <span className="flex-1">{label}</span>
            <span className="tabular font-medium text-text">{value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
