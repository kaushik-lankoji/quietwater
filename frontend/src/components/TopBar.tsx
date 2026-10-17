import { cls } from "../format";
import type { Config, Snapshot } from "../types";
import type { Link } from "../useLive";
import { Icon, Logo } from "./Icon";

const SPEEDS = [0.5, 1, 2, 5, 10];

export function TopBar({
  snap,
  config,
  link,
  theme,
  onTheme,
  onControl,
  onScenario,
  onMode,
}: {
  snap: Snapshot;
  config: Config;
  link: Link;
  theme: "dark" | "light";
  onTheme: () => void;
  onControl: (action: string, speed?: number) => void;
  onScenario: (id: string, seed?: number) => void;
  onMode: (recovery: boolean) => void;
}) {
  const recovery = snap.mode === "recovery";
  const modeText = config.rules.modes[snap.mode];
  const progress = Math.min(100, (snap.t / snap.scenario.duration_s) * 100);
  return (
    <header className="topbar">
      <div className="brand">
        <Logo />
        <div>
          <div className="brand-name">Quietwater</div>
          <div className="brand-tag">The gentlest response that works</div>
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
      <div className="clock-block" aria-label={`Harbor time ${snap.clock}`}>
        <span className="clock">{snap.clock}</span>
        <span className="progress" aria-hidden>
          <span style={{ width: `${progress}%` }} />
        </span>
      </div>
      <div className="controls">
        <button
          className="btn icon-only"
          onClick={() => onControl(snap.running ? "pause" : "play")}
          aria-label={snap.running ? "Pause (space)" : "Play (space)"}
          title={snap.running ? "Pause (space)" : "Play (space)"}
        >
          <Icon name={snap.running ? "pause" : "play"} />
        </button>
        <button className="btn icon-only" onClick={() => onControl("step")} aria-label="Step" title="Step">
          <Icon name="step" />
        </button>
        <button className="btn icon-only" onClick={() => onControl("restart")} aria-label="Replay from start" title="Replay from start">
          <Icon name="replay" />
        </button>
        {snap.scenario.id === "random" && (
          <button
            className="btn icon-only"
            onClick={() => onScenario("random", Math.floor(Math.random() * 100000))}
            aria-label="New random seed"
            title="New random seed"
          >
            <Icon name="shuffle" />
          </button>
        )}
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
      <button className="btn icon-only ghost" onClick={onTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
        <Icon name={theme === "dark" ? "sun" : "moon"} />
      </button>
      <span className={cls("link-dot", link)}>{link === "live" ? "live" : link === "lost" ? "reconnecting" : "connecting"}</span>
    </header>
  );
}
