import { useEffect, useRef, useState } from "react";
import type { Receipt, Snapshot, TwistEntry } from "./types";

const MAX_RECEIPTS = 2000;

export type Link = "connecting" | "live" | "lost";

export interface Live {
  snap: Snapshot | null;
  receipts: Receipt[];
  history: TwistEntry[];
  link: Link;
}

export function useLive(): Live {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [history, setHistory] = useState<TwistEntry[]>([]);
  const [link, setLink] = useState<Link>("connecting");
  const run = useRef<number | null>(null);

  useEffect(() => {
    let es: EventSource | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      es = new EventSource("/api/stream");
      es.addEventListener("hello", (e) => {
        const data = JSON.parse((e as MessageEvent).data) as Snapshot & { history: TwistEntry[] };
        run.current = data.run;
        setSnap(data);
        setReceipts(data.receipts.slice(-MAX_RECEIPTS));
        setHistory(data.history);
        setLink("live");
      });
      es.addEventListener("tick", (e) => {
        const data = JSON.parse((e as MessageEvent).data) as Snapshot;
        const fresh = run.current !== data.run;
        run.current = data.run;
        setSnap(data);
        if (fresh) setReceipts(data.receipts);
        else if (data.receipts.length) setReceipts((prev) => [...prev, ...data.receipts].slice(-MAX_RECEIPTS));
        setLink("live");
      });
      es.addEventListener("history", (e) => {
        setHistory((JSON.parse((e as MessageEvent).data) as { history: TwistEntry[] }).history);
      });
      es.onerror = () => {
        setLink("lost");
        es?.close();
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      es?.close();
    };
  }, []);

  return { snap, receipts, history, link };
}
