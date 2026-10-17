import { cls } from "../format";
import type { Budget, ScenarioInfo } from "../types";
import type { Link } from "../useLive";
import { Icon } from "./Icon";

export function BudgetCard({
  budget,
  clock,
  scenario,
  seed,
  scenarios,
  link,
  onScenario,
  onOpen,
}: {
  budget: Budget;
  clock: string;
  scenario: string;
  seed: number;
  scenarios: ScenarioInfo[];
  link: Link;
  onScenario: (id: string) => void;
  onOpen: () => void;
}) {
  const hot = budget.need_you > 0;
  const random = scenarios.find((s) => s.id === scenario)?.random;
  return (
    <section className="budget glass" aria-label="Alert budget">
      <button type="button" className={cls("budget-main", hot && "hot")} onClick={onOpen} aria-label={`${budget.need_you} need you. Open hand-off`}>
        <span className="budget-need">
          <span className="budget-n">{budget.need_you}</span>
          <span className="budget-l">need you{budget.watching > 0 ? ` · ${budget.watching} watching` : ""}</span>
        </span>
        <span className="budget-quiet">
          <span className="budget-quiet-n">{budget.quiet}</span> handled quietly
        </span>
      </button>
      <div className="budget-foot">
        <label className="scenario-select">
          <select value={scenario} onChange={(e) => onScenario(e.target.value)} aria-label="Scenario">
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
          <Icon name="chevronDown" size={14} />
        </label>
        <span className={cls("budget-clock", link !== "live" && "lost")}>{link === "live" ? clock : "Reconnecting"}</span>
      </div>
      {random && <div className="budget-seed">Seed {seed} · R replays it</div>}
    </section>
  );
}
