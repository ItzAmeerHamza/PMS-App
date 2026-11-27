import Link from "next/link";
import { Failure, Empty } from "@/components/States";
import { Filters, Pager } from "@/components/Filters";
import { day, money } from "@/lib/format";
import { apiQuery, load, shopOptions, type Page } from "@/lib/load";
import { pageCount, type PageQuery } from "@/lib/view";

type Product = { shop_id: string; public_id: string; sku: string; name: string; quantity: number; reorder_level: number | null; nearest_expiry: string | null; unit_price: string | null };

const LIMIT = 50;

export default async function InventoryPage({ searchParams }: { searchParams: Promise<PageQuery> }) {
  const query = await searchParams;
  const [shops, result] = await Promise.all([
    shopOptions(),
    load<Page<Product>>(`/api/v1/admin/inventory?${apiQuery(query, LIMIT)}`),
  ]);
  if (!result.ok) return <Failure />;
  const page = Math.max(1, Number(query.page) || 1);
  return (
    <div>
      <h1 className="text-2xl font-semibold">Inventory</h1>
      <p className="mb-4 mt-1 text-sm text-muted">Quantities come from stock movements. This screen cannot change them.</p>
      <Filters path="/inventory" query={query} shops={shops} search lowStock />
      {result.data.items.length === 0 ? <Empty>No products match.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-muted"><tr>
              <th className="p-3">Product</th><th className="p-3">SKU</th><th className="p-3">Qty</th><th className="p-3">Reorder</th><th className="p-3">Nearest expiry</th><th className="p-3">Price</th>
            </tr></thead>
            <tbody>
              {result.data.items.map((row) => (
                <tr key={`${row.shop_id}-${row.public_id}`} className="border-b border-line last:border-0">
                  <td className="p-3"><Link className="text-teal underline" href={`/inventory/${row.public_id}?shop=${row.shop_id}`}>{row.name}</Link></td>
                  <td className="p-3">{row.sku}</td>
                  <td className="p-3">{row.quantity}{(row.reorder_level ?? 0) >= row.quantity ? " · low" : ""}</td>
                  <td className="p-3">{row.reorder_level ?? "—"}</td>
                  <td className="p-3">{day(row.nearest_expiry)}</td>
                  <td className="p-3">{money(row.unit_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager path="/inventory" query={query} page={page} pages={pageCount(result.data.total, LIMIT)} />
    </div>
  );
}
