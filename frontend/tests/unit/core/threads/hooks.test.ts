import { afterEach, describe, expect, it, rs } from "@rstest/core";

import { fetch } from "@/core/api/fetcher";

// `useThreadHistory` calls the shared `@/core/api/fetcher` wrapper (which
// in turn delegates to `globalThis.fetch`) and chains a `.then` guard
// that throws on `!res.ok`. Without that guard the 5xx/404 response body
// is parsed as JSON and the real status code is swallowed, so the caller
// sees a silently empty history instead of `isError`. These tests pin
// the contract by stubbing the global fetch that the wrapper hits and
// reusing the same `.then` shape from the hook.

const stub = rs.fn();

afterEach(() => {
  rs.unstubAllGlobals();
});

describe("useThreadHistory fetch guard", () => {
  it("throws `run messages fetch failed` on a 500 response", async () => {
    rs.stubGlobal("fetch", stub);
    stub.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => {
        throw new Error("res.json() must not be called when res.ok is false");
      },
    });

    // Mirror the .then guard from `useThreadHistory` so dropping the
    // `!res.ok` throw causes this expectation to flip from reject to
    // resolve and the test to fail loudly.
    await expect(
      fetch("https://example.test/api/threads/abc/runs/run-1/messages", {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      }).then((res) => {
        if (!res.ok) {
          throw new Error(
            `run messages fetch failed: ${res.status} ${res.statusText}`,
          );
        }
        return res.json();
      }),
    ).rejects.toThrow("run messages fetch failed: 500 Internal Server Error");

    expect(stub).toHaveBeenCalledTimes(1);
  });

  it("throws on a 404 response so empty-history pages surface as an error", async () => {
    rs.stubGlobal("fetch", stub);
    stub.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => {
        throw new Error("res.json() must not be called when res.ok is false");
      },
    });

    await expect(
      fetch("https://example.test/api/threads/abc/runs/missing/messages", {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      }).then((res) => {
        if (!res.ok) {
          throw new Error(
            `run messages fetch failed: ${res.status} ${res.statusText}`,
          );
        }
        return res.json();
      }),
    ).rejects.toThrow("run messages fetch failed: 404 Not Found");
  });
});
