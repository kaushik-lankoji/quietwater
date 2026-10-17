import { Icon } from "./Icon";

export function ScenarioButton() {
  return (
    <button type="button" className="scenario-button" aria-label="New scenario" onClick={() => {}}>
      <Icon name="plus" size={26} />
    </button>
  );
}
