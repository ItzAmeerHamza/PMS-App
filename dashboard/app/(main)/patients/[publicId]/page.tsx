import Link from "next/link";
import { Failure } from "@/components/States";
import { day } from "@/lib/format";
import { load } from "@/lib/load";

type Visit = { public_id: string; prescribed_at: string | null; status: string; diagnosis: string | null; items: { medicine_name: string | null; quantity: number }[] };
type Detail = { first_name: string; last_name: string; phone: string; allergies: string | null; deleted: boolean; prescriptions: Visit[] };

export default async function PatientPage({ params, searchParams }: { params: Promise<{ publicId: string }>; searchParams: Promise<{ shop?: string }> }) {
  const { publicId } = await params;
  const { shop } = await searchParams;
  if (!shop) return <Failure />;
  const result = await load<Detail>(`/api/v1/admin/patients/${publicId}?shop_id=${shop}`);
  if (!result.ok) return <Failure />;
  const patient = result.data;
  return (
    <div>
      <Link className="text-sm text-teal underline" href={`/patients?shop=${shop}`}>Back to patients</Link>
      <h1 className="mt-2 text-2xl font-semibold">{patient.first_name} {patient.last_name}</h1>
      <p className="text-sm text-muted">{patient.phone}{patient.deleted ? " · removed at the shop" : ""}</p>
      {patient.allergies ? <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm">Allergies: {patient.allergies}</p> : null}
      <h2 className="mb-2 mt-6 font-medium">Visits, oldest first</h2>
      {patient.prescriptions.length === 0 ? <p className="text-sm text-muted">No prescriptions.</p> : (
        <ol className="space-y-3 text-sm">
          {patient.prescriptions.map((visit) => (
            <li key={visit.public_id} className="rounded-xl border border-line bg-white p-3">
              <p>{day(visit.prescribed_at)} · {visit.status}{visit.diagnosis ? ` · ${visit.diagnosis}` : ""}</p>
              <ul className="mt-1 text-muted">
                {visit.items.map((item, index) => <li key={index}>{item.medicine_name || "Medicine"} · qty {item.quantity}</li>)}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
