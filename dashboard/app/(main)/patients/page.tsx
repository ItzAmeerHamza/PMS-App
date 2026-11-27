import Link from "next/link";
import { Empty, Failure } from "@/components/States";
import { Filters, Pager } from "@/components/Filters";
import { apiQuery, load, shopOptions, type Page } from "@/lib/load";
import { pageCount, type PageQuery } from "@/lib/view";

type Patient = { shop_id: string; public_id: string; first_name: string; last_name: string; phone: string };

const LIMIT = 50;

export default async function PatientsPage({ searchParams }: { searchParams: Promise<PageQuery> }) {
  const query = await searchParams;
  const [shops, result] = await Promise.all([
    shopOptions(),
    load<Page<Patient>>(`/api/v1/admin/patients?${apiQuery(query, LIMIT)}`),
  ]);
  if (!result.ok) return <Failure />;
  const page = Math.max(1, Number(query.page) || 1);
  return (
    <div>
      <h1 className="text-2xl font-semibold">Patients</h1>
      <p className="mb-4 mt-1 text-sm text-muted">Visible only after sign-in. Patients cannot sign in here.</p>
      <Filters path="/patients" query={query} shops={shops} search />
      {result.data.items.length === 0 ? <Empty>No patients match.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-muted"><tr><th className="p-3">Name</th><th className="p-3">Phone</th></tr></thead>
            <tbody>
              {result.data.items.map((row) => (
                <tr key={`${row.shop_id}-${row.public_id}`} className="border-b border-line last:border-0">
                  <td className="p-3"><Link className="text-teal underline" href={`/patients/${row.public_id}?shop=${row.shop_id}`}>{row.first_name} {row.last_name}</Link></td>
                  <td className="p-3">{row.phone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager path="/patients" query={query} page={page} pages={pageCount(result.data.total, LIMIT)} />
    </div>
  );
}
