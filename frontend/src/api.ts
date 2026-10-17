import type { Config, HandoffItem, Mode } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => request<Config>("GET", "/api/config"),
  control: (action: string, speed?: number) => request("POST", "/api/sim/control", { action, speed }),
  scenario: (name: string, seed?: number) => request("POST", "/api/sim/scenario", { name, seed }),
  mode: (mode: Mode) => request("POST", "/api/mode", { mode, load_scenario: true }),
  act: (id: string, action: "approve" | "reject" | "watch" | "send", operator: string, note?: string) =>
    request<HandoffItem>("POST", `/api/handoff/${id}`, { action, operator, note }),
  exportUrl: (format: "json" | "csv") => `/api/audit/export?format=${format}`,
};
