import type { ReactNode } from "react";

function renderHeader(header: string) {
  return (
    <th key={header} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
      {header}
    </th>
  );
}

/**
 * Draws a table that scrolls by itself when it does not fit, so the page never does.
 *
 * Exists so every inventory looks the same.
 *
 * @param props.headers - The titles of the columns.
 * @param props.children - The rows.
 * @returns The table.
 */
export function DataTable({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-100 text-slate-600">
          <tr>{headers.map(renderHeader)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100 [&_td]:px-3 [&_td]:py-2">{children}</tbody>
      </table>
    </div>
  );
}
