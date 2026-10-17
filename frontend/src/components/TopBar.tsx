import { cls } from "../format";
import type { Config, Snapshot } from "../types";
import type { Link } from "../useLive";
import { Icon, Logo } from "./Icon";

const SPEEDS = [1, 2, 5];

export function TopBar({
  snap,
  config,
  link,
  onControl,
  onScenario,
  onMode,
}: {
  snap: Snapshot;
  config: Config;
  link: Link;
  onControl: (action: string, speed?: number) => void;
  onScenario: (id: string) => void;
  onMode: (recovery: boolean) => void;
}) {
  const recovery = snap.mode === "recovery";
  const modeText = config.rules.modes[snap.mode];
  return (
    <header className="topbar">
      <div className="brand">
        <Logo />
        <div>
          <div className="brand-name">Quietwater</div>
        </div>
      </div>
      <span className="mode-chip" title={modeText.customer}>
        {modeText.title}
      </span>
      <select
        className="select"
        value={snap.scenario.id}
        onChange={(e) => onScenario(e.target.value)}
        aria-label="Scenario"
      >
        {config.scenarios.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </select>
      <span className="topbar-spacer" />
      <span className="clock" aria-label={`Harbor time ${snap.clock}`}>
        {snap.clock}
      </span>
      <div className="controls">
        <button
          className="btn icon-only"
          onClick={() => onControl(snap.running ? "pause" : "play")}
          aria-label={snap.running ? "Pause (space)" : "Play (space)"}
          title={snap.running ? "Pause (space)" : "Play (space)"}
        >
          <Icon name={snap.running ? "pause" : "play"} />
        </button>
        <button className="btn icon-only" onClick={() => onControl("restart")} aria-label="Replay from start" title="Replay from start">
          <Icon name="replay" />
        </button>
        <div className="segmented" role="group" aria-label="Speed">
          {SPEEDS.map((s) => (
            <button key={s} aria-pressed={snap.speed === s} onClick={() => onControl("speed", s)}>
              {s}×
            </button>
          ))}
        </div>
      </div>
      <button
        className="switch"
        role="switch"
        aria-checked={recovery}
        onClick={() => onMode(!recovery)}
        title="Switch the same engine into lost-vehicle recovery"
      >
        <span className="track" />
        Quiet Tuesday
      </button>
      <span className={cls("link-dot", link)}>{link === "live" ? "live" : link === "lost" ? "reconnecting" : "connecting"}</span>
    </header>
  );
}
