import { Icon } from "./Icon";

export function ScenarioButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="scenario-button"
      aria-label="New random scenario"
      title="New random scenario"
      onClick={onClick}
    >
      <Icon name="plus" size={26} />
    </button>
  );
}
