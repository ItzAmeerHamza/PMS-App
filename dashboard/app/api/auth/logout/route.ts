import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/cloud";

export async function POST(request: NextRequest) {
  const token = request.cookies.get("pharmacare_session")?.value;
  const csrf = request.cookies.get("pharmacare_csrf")?.value || "";
  const form = await request.formData().catch(() => null);
  if (!csrf || form?.get("csrf") !== csrf) {
    return NextResponse.json({ detail: "CSRF check failed" }, { status: 403 });
  }
  if (token) {
    try {
      await fetch(`${apiBase()}/api/v1/owner/logout`, {
        method: "POST",
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}`, "X-CSRF-Token": csrf },
      });
    } catch {
      // The local cookie is cleared either way. The cloud session expires on its own if this call fails.
    }
  }
  const response = NextResponse.redirect(new URL("/login", request.url), 303);
  response.cookies.set("pharmacare_session", "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
