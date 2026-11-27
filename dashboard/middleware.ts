import { NextResponse, type NextRequest } from "next/server";
import { needsSession } from "@/lib/view";

export function middleware(request: NextRequest) {
  if (!needsSession(request.nextUrl.pathname)) return NextResponse.next();
  if (!request.cookies.get("pharmacare_session")?.value) {
    const login = new URL("/login", request.url);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
