import { cls } from "../format";
import { Icon, type IconName } from "./Icon";

function Tile({
  icon,
  label,
  onClick,
  active,
  shortcut,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  active?: boolean;
  shortcut?: string;
}) {
  return (
    <button
      type="button"
      className={cls("dock-tile", active && "active")}
      aria-pressed={active}
      aria-keyshortcuts={shortcut}
      onClick={onClick}
    >
      <Icon name={icon} size={24} />
      <span>{label}</span>
      <span className="tip" role="presentation">
        {label}
        {shortcut && <kbd>{shortcut}</kbd>}
      </span>
    </button>
  );
}

export function ControlDock({
  running,
  flood,
  sheet,
  onToggleRun,
  onReplay,
  onFlood,
  onTwist,
  onReceipts,
}: {
  running: boolean;
  flood: boolean;
  sheet: string | null;
  onToggleRun: () => void;
  onReplay: () => void;
  onFlood: () => void;
  onTwist: () => void;
  onReceipts: () => void;
}) {
  return (
    <nav className="dock glass" aria-label="Simulator controls">
      <Tile icon={running ? "pause" : "play"} label={running ? "Pause" : "Resume"} onClick={onToggleRun} active={!running} shortcut="Space" />
      <Tile icon="replay" label="Replay" onClick={onReplay} shortcut="R" />
      <Tile icon="flood" label="Flood" onClick={onFlood} active={flood} shortcut="F" />
      <Tile icon="sliders" label="Twist" onClick={onTwist} active={sheet === "twist"} shortcut="T" />
      <Tile icon="receipt" label="Receipts" onClick={onReceipts} active={sheet === "receipts"} />
    </nav>
  );
}
