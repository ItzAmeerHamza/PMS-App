import { describe, expect, it } from "vitest";
import { backlogText, clientAuthBody, detailQuery, listQuery, needsSession, pageCount, rowsOrEmpty } from "../lib/view";

describe("owner session gate", () => {
  it("rejects an anonymous page and allows login", () => {
    expect(needsSession("/")).toBe(true);
    expect(needsSession("/inventory")).toBe(true);
    expect(needsSession("/login")).toBe(false);
    expect(needsSession("/api/auth/login")).toBe(false);
  });
});

describe("sync backlog", () => {
  it("does not call a missing report zero", () => {
    expect(backlogText(null)).toBe("Not reported");
    expect(backlogText(undefined)).toBe("Not reported");
    expect(backlogText(0)).toBe("0 waiting to send");
    expect(backlogText(4)).toBe("4 waiting to send");
  });
});

describe("auth response", () => {
  it("strips the session token before it can reach the browser", () => {
    const body = clientAuthBody({ status: "totp", challenge: "abc", token: "pco_secret", expires_at: "t" });
    expect(body).toEqual({ status: "totp", challenge: "abc", expires_at: "t" });
    expect(JSON.stringify(body)).not.toContain("pco_secret");
  });
});

describe("lists", () => {
  it("changes the shop, page, and search sent to the API", () => {
    const first = listQuery({ shop: "shop-a", q: "para", page: "2" });
    const second = listQuery({ shop: "shop-b", q: "para", page: "2" });
    expect(first).toContain("shop_id=shop-a");
    expect(second).toContain("shop_id=shop-b");
    expect(first).toContain("offset=50");
    expect(first).not.toBe(second);
    expect(pageCount(120, 50)).toBe(3);
    expect(detailQuery("shop-a", { from: "2024-01-01", to: "2024-06-01" })).toBe(
      "shop_id=shop-a&date_from=2024-01-01&date_to=2024-06-01",
    );
  });

  it("shows nothing when the API failed, instead of an older page", () => {
    expect(rowsOrEmpty({ ok: false })).toEqual([]);
    expect(rowsOrEmpty({ ok: true, items: [{ id: 1 }] })).toEqual([{ id: 1 }]);
  });
});
