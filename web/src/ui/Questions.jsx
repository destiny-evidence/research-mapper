/** Questions as asked by LLMs, not implicit suggest-select flows */

import { answerLabels, asTrajectory } from "../derive.js";
import { Reasoning } from "./Reasoning.jsx";
import { ForkButton } from "./Fork.jsx";

const SHOWN = 3;

/** The thought behind a loop's question, matched by the key it asked under. */
const thoughtFor = (decision, trajectory) => {
  const [, index] = (decision?.key ?? "").split(":");
  return index ? asTrajectory(trajectory)[`thought_${index}`] : null;
};

/** The questions a step settled, each one a place the session can fork. */
export function Questions({
  decisions = [],
  trajectory = null,
  busy = false,
  onFork,
}) {
  if (!decisions.length) return null;
  const numbered = decisions.length > 1;
  return (
    <div class="questions">
      {decisions.map((decision, index) => {
        const chosen = answerLabels(decision);
        return (
          <div
            class={numbered ? "question-row" : "question-row sole"}
            key={decision.id}
          >
            {numbered ? <span class="question-n">{index + 1}</span> : null}
            <div>
              <div class="question-q">{decision.prompt}</div>
              <div class="question-a">
                {chosen.slice(0, SHOWN).map((label) => (
                  <span class="chose" key={label}>
                    {label}
                  </span>
                ))}
                {chosen.length > SHOWN ? (
                  <span class="chose more">+{chosen.length - SHOWN} more</span>
                ) : null}
              </div>
              <Reasoning text={thoughtFor(decision, trajectory)} />
              <ForkButton disabled={busy} onFork={() => onFork(decision)} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
