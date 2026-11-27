import Link from "next/link";
import { Failure } from "@/components/States";
import { day } from "@/lib/format";
import { load } from "@/lib/load";
import { detailQuery, type PageQuery } from "@/lib/view";

type Detail = {
  name: string; sku: string; quantity: number; reorder_level: number | null; manufacturer: string | null;
  batches: { batch_number: string; expiry_date: string; quantity: number }[];
  movements: { movement_type: string; quantity_delta: number; batch_number: string; occurred_at: string | null }[];
};

export default async function ProductPage({ params, searchParams }: { params: Promise<{ publicId: string }>; searchParams: Promise<PageQuery> }) {
  const { publicId } = await params;
  const query = await searchParams;
  const shop = query.shop;
  if (!shop) return <Failure />;
  const result = await load<Detail>(`/api/v1/admin/inventory/${publicId}?${detailQuery(shop, query)}`);
  if (!result.ok) return <Failure />;
  const product = result.data;
  return (
    <div>
      <Link className="text-sm text-teal underline" href={`/inventory?shop=${shop}`}>Back to inventory</Link>
      <h1 className="mt-2 text-2xl font-semibold">{product.name}</h1>
      <p className="text-sm text-muted">{product.sku} · {product.manufacturer || "No company"} · {product.quantity} on hand · reorder {product.reorder_level ?? "—"}</p>
      <h2 className="mb-2 mt-6 font-medium">Batches</h2>
      {product.batches.length === 0 ? <p className="text-sm text-muted">No batches.</p> : (
        <ul className="text-sm">{product.batches.map((batch) => <li key={batch.batch_number}>{batch.batch_number} · {batch.quantity} · expires {day(batch.expiry_date)}</li>)}</ul>
      )}
      <h2 className="mb-2 mt-6 font-medium">Movement history</h2>
      <form className="mb-3 flex flex-wrap items-end gap-3" action={`/inventory/${publicId}`} method="get">
        <input type="hidden" name="shop" value={shop} />
        <label className="text-sm text-muted">From
          <input type="date" name="from" defaultValue={query.from || ""} className="mt-1 block rounded-lg border border-line px-3 py-2" />
        </label>
        <label className="text-sm text-muted">To
          <input type="date" name="to" defaultValue={query.to || ""} className="mt-1 block rounded-lg border border-line px-3 py-2" />
        </label>
        <button className="rounded-lg bg-teal px-4 py-2 text-sm text-white" type="submit">Apply</button>
      </form>
      <p className="mb-2 text-sm text-muted">The date filter changes this history only. Quantity on hand stays the current total.</p>
      {product.movements.length === 0 ? <p className="text-sm text-muted">No movements.</p> : (
        <ul className="space-y-1 text-sm">
          {product.movements.map((row, index) => (
            <li key={index}>{day(row.occurred_at)} · {row.movement_type} · {row.quantity_delta > 0 ? "+" : ""}{row.quantity_delta} · batch {row.batch_number}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
