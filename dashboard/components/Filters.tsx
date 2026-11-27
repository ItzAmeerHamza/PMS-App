import type { PageQuery } from "@/lib/view";

export function Filters({
  path,
  query,
  shops,
  search = false,
  dates = false,
  lowStock = false,
}: {
  path: string;
  query: PageQuery;
  shops: { id: string; name: string }[];
  search?: boolean;
  dates?: boolean;
  lowStock?: boolean;
}) {
  return (
    <form className="mb-4 flex flex-wrap items-end gap-3" action={path} method="get">
      <label className="text-sm text-muted">
        Shop
        <select name="shop" defaultValue={query.shop || ""} className="mt-1 block rounded-lg border border-line bg-white px-3 py-2 text-ink">
          <option value="">All shops</option>
          {shops.map((shop) => (
            <option key={shop.id} value={shop.id}>{shop.name}</option>
          ))}
        </select>
      </label>
      {search ? (
        <label className="text-sm text-muted">
          Search
          <input name="q" defaultValue={query.q || ""} className="mt-1 block rounded-lg border border-line px-3 py-2" />
        </label>
      ) : null}
      {dates ? (
        <>
          <label className="text-sm text-muted">
            From
            <input type="date" name="from" defaultValue={query.from || ""} className="mt-1 block rounded-lg border border-line px-3 py-2" />
          </label>
          <label className="text-sm text-muted">
            To
            <input type="date" name="to" defaultValue={query.to || ""} className="mt-1 block rounded-lg border border-line px-3 py-2" />
          </label>
        </>
      ) : null}
      {lowStock ? (
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input type="checkbox" name="low" value="1" defaultChecked={query.low === "1"} />
          Low stock only
        </label>
      ) : null}
      <button className="rounded-lg bg-teal px-4 py-2 text-sm text-white" type="submit">Apply</button>
    </form>
  );
}

export function Pager({ path, query, page, pages }: { path: string; query: PageQuery; page: number; pages: number }) {
  function href(next: number) {
    const params = new URLSearchParams();
    if (query.shop) params.set("shop", query.shop);
    if (query.q) params.set("q", query.q);
    if (query.from) params.set("from", query.from);
    if (query.to) params.set("to", query.to);
    if (query.low) params.set("low", query.low);
    params.set("page", String(next));
    return `${path}?${params.toString()}`;
  }
  return (
    <div className="mt-4 flex items-center gap-3 text-sm">
      {page > 1 ? <a className="text-teal underline" href={href(page - 1)}>Previous</a> : <span className="text-muted">Previous</span>}
      <span>Page {page} of {pages}</span>
      {page < pages ? <a className="text-teal underline" href={href(page + 1)}>Next</a> : <span className="text-muted">Next</span>}
    </div>
  );
}
