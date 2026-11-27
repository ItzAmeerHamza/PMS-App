export function Loading() {
  return <p className="text-muted">Loading…</p>;
}

export function Empty({ children }: { children: string }) {
  return <p className="rounded-xl border border-dashed border-line bg-white px-4 py-8 text-center text-muted">{children}</p>;
}

export function Failure() {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-6 text-red-900">
      <p className="font-medium">The owner service did not respond.</p>
      <p className="mt-1 text-sm">This page is not showing numbers from an earlier visit.</p>
    </div>
  );
}
