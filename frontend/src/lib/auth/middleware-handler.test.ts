import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { applyAuthMiddleware } from "./middleware-handler";

describe("auth path middleware", () => {
  it("rewrites POST /signup to /api/signup", () => {
    const req = new NextRequest("http://localhost:3000/signup", {
      method: "POST",
    });
    const res = applyAuthMiddleware(req, false);
    expect(res.headers.get("x-middleware-rewrite")).toBe(
      "http://localhost:3000/api/signup",
    );
  });

  it("rewrites POST /login to /api/login", () => {
    const req = new NextRequest("http://localhost:3000/login", {
      method: "POST",
    });
    const res = applyAuthMiddleware(req, false);
    expect(res.headers.get("x-middleware-rewrite")).toBe(
      "http://localhost:3000/api/login",
    );
  });

  it("does not rewrite GET /signup", () => {
    const req = new NextRequest("http://localhost:3000/signup", {
      method: "GET",
    });
    const res = applyAuthMiddleware(req, false);
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
    expect(res.headers.get("location")).toBeNull();
  });

  it("redirects unauthenticated GET / to /login", () => {
    const req = new NextRequest("http://localhost:3000/", { method: "GET" });
    const res = applyAuthMiddleware(req, false);
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("allows authenticated GET /", () => {
    const req = new NextRequest("http://localhost:3000/", { method: "GET" });
    const res = applyAuthMiddleware(req, true);
    expect(res.headers.get("location")).toBeNull();
  });
});
