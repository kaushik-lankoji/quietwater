export function DualUseToggle({ on, onChange, disabled }: { on: boolean; onChange: (on: boolean) => void; disabled?: boolean }) {
  return (
    <div className="dual-use glass">
      <div className="dual-use-text">
        <span className="dual-use-title">Dual-use</span>
        <span className="dual-use-status">{on ? "Vehicle recovery" : "Harbor security"}</span>
      </div>
      <button
        type="button"
        className="switch"
        role="switch"
        aria-checked={on}
        aria-label="Dual-use: vehicle recovery"
        disabled={disabled}
        onClick={() => onChange(!on)}
      >
        <span className="switch-thumb" />
      </button>
    </div>
  );
}
