/** Pure display rules. No network, no secrets. */

export type PageQuery = {
  shop?: string;
  q?: string;
  page?: string;
  from?: string;
  to?: string;
  low?: string;
};

export function needsSession(pathname: string): boolean {
  return !(pathname === "/login" || pathname.startsWith("/login/") || pathname.startsWith("/api/auth"));
}

export function backlogText(reported: number | null | undefined): string {
  if (reported === null || reported === undefined) return "Not reported";
  return `${reported} waiting to send`;
}

export function clientAuthBody<T extends { token?: string }>(body: T): Omit<T, "token"> {
  const rest = { ...body };
  delete rest.token;
  return rest;
}

export function listQuery(query: PageQuery, limit = 50): string {
  const page = Math.max(1, Number(query.page) || 1);
  const params = new URLSearchParams();
  if (query.shop) params.set("shop_id", query.shop);
  if (query.q) params.set("search", query.q);
  if (query.from) params.set("date_from", query.from);
  if (query.to) params.set("date_to", query.to);
  if (query.low === "1") params.set("low_stock", "true");
  params.set("limit", String(limit));
  params.set("offset", String((page - 1) * limit));
  return params.toString();
}

export function detailQuery(shop: string, query: PageQuery): string {
  const params = new URLSearchParams();
  params.set("shop_id", shop);
  if (query.from) params.set("date_from", query.from);
  if (query.to) params.set("date_to", query.to);
  return params.toString();
}

export function pageCount(total: number, limit: number): number {
  return Math.max(1, Math.ceil(total / limit));
}

/** A failed load has no rows. Callers must not keep a previous page. */
export function rowsOrEmpty<T>(result: { ok: true; items: T[] } | { ok: false }): T[] {
  return result.ok ? result.items : [];
}
