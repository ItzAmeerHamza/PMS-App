import { Failure, Empty } from "@/components/States";
import { when } from "@/lib/format";
import { load } from "@/lib/load";
import { backlogText } from "@/lib/view";

type Shop = {
  id: string; name: string; created_at: string | null; last_sync_at: string | null;
  last_result: string | null; last_error_code: string | null; events_applied: number | null;
  reported_pending: number | null; reported_at: string | null;
};

export default async function ShopsPage() {
  const result = await load<{ items: Shop[] }>("/api/v1/admin/shops?limit=200");
  if (!result.ok) return <Failure />;
  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Shops</h1>
      {result.data.items.length === 0 ? <Empty>No shops registered.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-muted">
              <tr>
                <th className="p-3">Name</th><th className="p-3">Shop id</th><th className="p-3">Registered</th>
                <th className="p-3">Last sync</th><th className="p-3">Last result</th><th className="p-3">Backlog</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((shop) => (
                <tr key={shop.id} className="border-b border-line last:border-0">
                  <td className="p-3 font-medium">{shop.name}</td>
                  <td className="p-3 font-mono text-xs">{shop.id}</td>
                  <td className="p-3">{when(shop.created_at)}</td>
                  <td className="p-3">{shop.last_sync_at ? when(shop.last_sync_at) : "No sync yet"}</td>
                  <td className="p-3">{shop.last_error_code || shop.last_result || "—"}</td>
                  <td className="p-3">{backlogText(shop.reported_pending)}{shop.reported_at ? ` (as of ${when(shop.reported_at)})` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
