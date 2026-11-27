import { NextRequest, NextResponse } from "next/server";
import { cloudCsrf, cloudPost } from "@/lib/cloud";

const SESSION = "pharmacare_session";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const csrf = request.cookies.get("pharmacare_csrf")?.value || "";
  if (!body?.challenge || !body?.code || !body?.csrf || body.csrf !== csrf) {
    return NextResponse.json({ detail: "CSRF check failed" }, { status: 403 });
  }
  try {
    const proof = await cloudCsrf();
    const response = await cloudPost("/api/v1/owner/totp", { challenge: body.challenge, code: body.code }, proof.token, proof.cookie);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return NextResponse.json({ detail: payload.detail || "The code was not accepted" }, { status: response.status });
    const out = NextResponse.json({ ok: true, expires_at: payload.expires_at });
    out.cookies.set(SESSION, payload.token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 12,
    });
    return out;
  } catch {
    return NextResponse.json({ detail: "The owner service did not respond" }, { status: 503 });
  }
}
