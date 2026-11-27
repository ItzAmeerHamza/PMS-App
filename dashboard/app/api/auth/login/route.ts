import { NextRequest, NextResponse } from "next/server";
import { cloudCsrf, cloudPost } from "@/lib/cloud";
import { clientAuthBody } from "@/lib/view";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const csrf = request.cookies.get("pharmacare_csrf")?.value || "";
  if (!body?.email || !body?.password || !body?.csrf || body.csrf !== csrf) {
    return NextResponse.json({ detail: "CSRF check failed" }, { status: 403 });
  }
  try {
    const proof = await cloudCsrf();
    const response = await cloudPost("/api/v1/owner/login", { email: body.email, password: body.password }, proof.token, proof.cookie);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return NextResponse.json({ detail: payload.detail || "Sign-in failed" }, { status: response.status });
    return NextResponse.json(clientAuthBody(payload));
  } catch {
    return NextResponse.json({ detail: "The owner service did not respond" }, { status: 503 });
  }
}
