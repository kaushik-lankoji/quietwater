import { Icon } from "./Icon";

export function ScenarioButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="scenario-button" title="New variation of this scenario" onClick={onClick}>
      <Icon name="plus" size={20} />
      Generate scenario
    </button>
  );
}
