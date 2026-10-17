import type { Config, HandoffItem, Impact, FieldChange, Mode, RulesData, TwistEntry } from "./types";

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
      detail = res.statusText;
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export interface TwistPayload {
  rules?: RulesData;
  yaml?: string;
  ops?: { op?: string; path: string; value?: unknown }[];
  scenario?: string;
}

export interface PreviewResult {
  changes: FieldChange[];
  impact: Impact;
  candidate: RulesData;
}

export const api = {
  config: () => request<Config>("GET", "/api/config"),
  rulesText: () => request<{ text: string; version: number }>("GET", "/api/rules"),
  control: (action: string, speed?: number) => request("POST", "/api/sim/control", { action, speed }),
  scenario: (name: string, seed?: number) => request("POST", "/api/sim/scenario", { name, seed }),
  mode: (mode: Mode) => request("POST", "/api/mode", { mode, load_scenario: true }),
  act: (id: string, action: "approve" | "reject" | "watch" | "send", operator: string, note?: string) =>
    request<HandoffItem>("POST", `/api/handoff/${id}`, { action, operator, note }),
  preview: (payload: TwistPayload) => request<PreviewResult>("POST", "/api/twist/preview", payload),
  apply: (payload: TwistPayload & { title: string; note: string; source: "ui" | "preset" }) =>
    request<TwistEntry>("POST", "/api/twist/apply", payload),
  revert: (id: string) => request<TwistEntry>("POST", `/api/twist/revert/${id}`),
  exportUrl: (format: "json" | "csv") => `/api/audit/export?format=${format}`,
};
