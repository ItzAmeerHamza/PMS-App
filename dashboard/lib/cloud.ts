import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const SESSION = "pharmacare_session";

export class CloudError extends Error {
  status: number;
  constructor(status: number) {
    super("The owner service did not respond");
    this.status = status;
  }
}

export function apiBase(): string {
  const base = process.env.CLOUD_API_URL?.trim();
  if (!base) throw new CloudError(500);
  return base.replace(/\/$/, "");
}

export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION)?.value || null;
}

export async function cloudGet<T>(path: string): Promise<T> {
  const token = await sessionToken();
  if (!token) redirect("/login");
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
  } catch {
    throw new CloudError(503);
  }
  if (response.status === 401) redirect("/login");
  if (!response.ok) throw new CloudError(response.status);
  return response.json() as Promise<T>;
}

export async function cloudPost(path: string, body: unknown, csrfToken: string, csrfCookie: string): Promise<Response> {
  return fetch(`${apiBase()}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-CSRF-Token": csrfToken,
      Cookie: `pharmacare_csrf=${csrfCookie}`,
    },
    body: JSON.stringify(body),
  });
}

export async function cloudCsrf(): Promise<{ token: string; cookie: string }> {
  const response = await fetch(`${apiBase()}/api/v1/owner/csrf`, { cache: "no-store" });
  if (!response.ok) throw new CloudError(response.status);
  const token = (await response.json()).token as string;
  const raw = response.headers.get("set-cookie") || "";
  const match = raw.match(/pharmacare_csrf=([^;]+)/);
  return { token, cookie: match?.[1] || token };
}
