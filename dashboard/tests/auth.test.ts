import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { POST as login } from "../app/api/auth/login/route";
import { POST as logout } from "../app/api/auth/logout/route";

function jsonRequest(url: string, body: unknown, csrf?: string) {
  return new NextRequest(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(csrf ? { cookie: `pharmacare_csrf=${csrf}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

describe("owner sign-in and sign-out", () => {
  it("refuses a login that does not echo the CSRF cookie", async () => {
    const response = await login(jsonRequest("http://127.0.0.1:3000/api/auth/login", {
      email: "owner@example.test",
      password: "not-sent-anywhere",
      csrf: "mismatch",
    }, "expected"));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ detail: "CSRF check failed" });
  });

  it("refuses sign-out when the form value does not match the cookie", async () => {
    const request = new NextRequest("http://127.0.0.1:3000/api/auth/logout", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", cookie: "pharmacare_csrf=expected" },
      body: "csrf=mismatch",
    });
    const response = await logout(request);
    expect(response.status).toBe(403);
  });
});
