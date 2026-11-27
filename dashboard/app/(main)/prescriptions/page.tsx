import { Empty, Failure } from "@/components/States";
import { Filters, Pager } from "@/components/Filters";
import { day } from "@/lib/format";
import { apiQuery, load, shopOptions, type Page } from "@/lib/load";
import { pageCount, type PageQuery } from "@/lib/view";

type Item = { medicine_name: string | null; quantity: number; dosage: string | null; frequency: string | null; instructions: string | null };
type Row = { public_id: string; patient_name: string; status: string; prescribed_at: string | null; items: Item[] };

const LIMIT = 50;

export default async function PrescriptionsPage({ searchParams }: { searchParams: Promise<PageQuery> }) {
  const query = await searchParams;
  const [shops, result] = await Promise.all([
    shopOptions(),
    load<Page<Row>>(`/api/v1/admin/prescriptions?${apiQuery(query, LIMIT)}`),
  ]);
  if (!result.ok) return <Failure />;
  const page = Math.max(1, Number(query.page) || 1);
  return (
    <div>
      <h1 className="text-2xl font-semibold">Prescriptions</h1>
      <Filters path="/prescriptions" query={query} shops={shops} search dates />
      {result.data.items.length === 0 ? <Empty>No prescriptions match.</Empty> : (
        <div className="space-y-3">
          {result.data.items.map((row) => (
            <article key={row.public_id} className="rounded-xl border border-line bg-white p-4 text-sm">
              <p className="font-medium">{row.patient_name} · {day(row.prescribed_at)} · {row.status}</p>
              <ul className="mt-2 space-y-1 text-muted">
                {row.items.map((item, index) => (
                  <li key={index}>{item.medicine_name || "Medicine"} · qty {item.quantity}{item.dosage ? ` · ${item.dosage}` : ""}{item.frequency ? ` · ${item.frequency}` : ""}{item.instructions ? ` · ${item.instructions}` : ""}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
      <Pager path="/prescriptions" query={query} page={page} pages={pageCount(result.data.total, LIMIT)} />
    </div>
  );
}
