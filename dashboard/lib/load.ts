import { cloudGet, CloudError } from "./cloud";
import { listQuery, type PageQuery } from "./view";

export function rethrowRedirect(error: unknown): void {
  if (error && typeof error === "object" && "digest" in error && String((error as { digest?: string }).digest).includes("NEXT_REDIRECT")) {
    throw error;
  }
}

export async function load<T>(path: string): Promise<{ ok: true; data: T } | { ok: false }> {
  try {
    return { ok: true, data: await cloudGet<T>(path) };
  } catch (error) {
    rethrowRedirect(error);
    if (error instanceof CloudError && error.status === 401) throw error;
    return { ok: false };
  }
}

export type ShopOption = { id: string; name: string };
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export async function shopOptions(): Promise<ShopOption[]> {
  const result = await load<Page<ShopOption>>("/api/v1/admin/shops?limit=200");
  return result.ok ? result.data.items : [];
}

export function apiQuery(query: PageQuery, limit = 50): string {
  return listQuery(query, limit);
}
