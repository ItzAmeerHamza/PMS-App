import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const next = request.nextUrl.searchParams.get("next") || "/login";
  const token = crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");
  const response = NextResponse.redirect(new URL(next, request.url));
  response.cookies.set("pharmacare_csrf", token, {
    httpOnly: false,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return response;
}
