import { Failure, Empty } from "@/components/States";
import { when } from "@/lib/format";
import { load } from "@/lib/load";
import { backlogText } from "@/lib/view";

type Row = {
  shop_id: string; shop_name: string; last_sync_at: string | null; last_applied_sequence: number | null;
  events_applied: number | null; last_result: string | null; last_error_code: string | null;
  reported_pending: number | null; reported_failed: number | null; reported_at: string | null;
};

export default async function SyncPage() {
  const result = await load<{ items: Row[] }>("/api/v1/admin/sync-status?limit=200");
  if (!result.ok) return <Failure />;
  return (
    <div>
      <h1 className="text-2xl font-semibold">Sync</h1>
      <p className="mb-4 mt-1 text-sm text-muted">These figures are what each shop last reported. A shop that has not reported is not shown as empty or fully synced.</p>
      {result.data.items.length === 0 ? <Empty>No shops registered.</Empty> : (
        <div className="grid gap-3">
          {result.data.items.map((shop) => (
            <article key={shop.shop_id} className="rounded-xl border border-line bg-white p-4 text-sm">
              <h2 className="font-medium">{shop.shop_name}</h2>
              <p className="mt-1 text-muted">Last successful sync: {shop.last_sync_at ? when(shop.last_sync_at) : "No sync yet"}</p>
              <p className="text-muted">Last event sequence: {shop.last_applied_sequence ?? "—"} · events applied: {shop.events_applied ?? "—"}</p>
              <p className="text-muted">Last result: {shop.last_error_code || shop.last_result || "—"}</p>
              <p className="mt-2">Backlog: {backlogText(shop.reported_pending)}{shop.reported_failed != null ? ` · ${shop.reported_failed} failed` : ""}</p>
              <p className="text-muted">Report time: {shop.reported_at ? when(shop.reported_at) : "No report yet"}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
