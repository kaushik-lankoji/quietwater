import { cls } from "../format";
import type { Budget } from "../types";

export function WatchSummary({ budget }: { budget: Budget }) {
  return (
    <section className="panel watch-summary" aria-label="Contact summary">
      <div className="stat quiet" title="Contacts that never needed a person">
        <div className="n">{budget.quiet}</div>
        <div className="l">handled quietly</div>
      </div>
      <div className={cls("stat need", budget.need_you > 0 && "hot")} title="Hand-offs waiting on you now">
        <div className="n">{budget.need_you}</div>
        <div className="l">need you{budget.watching > 0 ? ` · ${budget.watching} watching` : ""}</div>
      </div>
    </section>
  );
}
