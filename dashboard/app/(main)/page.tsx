import { Failure } from "@/components/States";
import { Filters } from "@/components/Filters";
import { day, when } from "@/lib/format";
import { load, shopOptions } from "@/lib/load";
import { backlogText, type PageQuery } from "@/lib/view";

type Overview = { shops: number; products: number; patients: number; prescriptions: number; units_on_hand: number };
type Movement = { product_name: string; movement_type: string; quantity_delta: number; occurred_at: string | null; shop_id: string };
type Visit = { patient_name: string; status: string; prescribed_at: string | null; shop_id: string };
type SyncRow = { shop_name: string; last_sync_at: string | null; reported_pending: number | null; reported_at: string | null };

export default async function Home({ searchParams }: { searchParams: Promise<PageQuery> }) {
  const query = await searchParams;
  const qs = new URLSearchParams();
  if (query.shop) qs.set("shop_id", query.shop);
  if (query.from) qs.set("date_from", query.from);
  if (query.to) qs.set("date_to", query.to);
  const suffix = qs.toString() ? `?${qs}` : "";
  const [shops, overview, movements, visits, sync] = await Promise.all([
    shopOptions(),
    load<Overview>(`/api/v1/admin/overview${query.shop ? `?shop_id=${query.shop}` : ""}`),
    load<{ items: Movement[] }>(`/api/v1/admin/movements${suffix}${suffix ? "&" : "?"}limit=8`),
    load<{ items: Visit[] }>(`/api/v1/admin/prescriptions${suffix}${suffix ? "&" : "?"}limit=8`),
    load<{ items: SyncRow[] }>("/api/v1/admin/sync-status?limit=200"),
  ]);
  if (!overview.ok || !movements.ok || !visits.ok || !sync.ok) return <Failure />;
  const cards = [
    ["Shops", overview.data.shops],
    ["Products", overview.data.products],
    ["Units on hand", overview.data.units_on_hand],
    ["Patients", overview.data.patients],
    ["Prescriptions", overview.data.prescriptions],
  ];
  return (
    <div>
      <h1 className="text-2xl font-semibold">Home</h1>
      <p className="mb-4 mt-1 text-sm text-muted">Counts are the replica as of this request. Recent rows follow the date filter.</p>
      <Filters path="/" query={query} shops={shops} dates />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {cards.map(([label, value]) => (
          <section key={String(label)} className="rounded-xl border border-line bg-white p-4">
            <p className="text-sm text-muted">{label}</p>
            <p className="mt-1 text-2xl font-semibold">{value}</p>
          </section>
        ))}
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-line bg-white p-4">
          <h2 className="font-medium">Recent movements</h2>
          {movements.data.items.length === 0 ? <p className="mt-3 text-sm text-muted">No movements in this view.</p> : (
            <ul className="mt-3 space-y-2 text-sm">
              {movements.data.items.map((row, index) => (
                <li key={index}>{row.product_name} · {row.movement_type} · {row.quantity_delta > 0 ? "+" : ""}{row.quantity_delta} · {day(row.occurred_at)}</li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-xl border border-line bg-white p-4">
          <h2 className="font-medium">Recent prescriptions</h2>
          {visits.data.items.length === 0 ? <p className="mt-3 text-sm text-muted">No prescriptions in this view.</p> : (
            <ul className="mt-3 space-y-2 text-sm">
              {visits.data.items.map((row, index) => (
                <li key={index}>{row.patient_name} · {row.status} · {day(row.prescribed_at)}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <section className="mt-4 rounded-xl border border-line bg-white p-4">
        <h2 className="font-medium">Last sync by shop</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {sync.data.items.map((row) => (
            <li key={row.shop_name}>
              <span className="font-medium">{row.shop_name}</span> · last sync {when(row.last_sync_at)} · backlog {backlogText(row.reported_pending)}
              {row.reported_at ? ` · reported ${when(row.reported_at)}` : ""}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
