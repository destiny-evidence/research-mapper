import { useState } from "preact/hooks";

const COMMUNITIES = ["hpv", "esea"];

/** Question, community, and which retrieval paths to run. */
export function NewSession({ onCreate, onCancel, busy }) {
  const [question, setQuestion] = useState("");
  const [community, setCommunity] = useState(COMMUNITIES[0]);
  const [mode, setMode] = useState("both");

  return (
    <>
      <div class="list-head">
        <span class="list-title">Ask a question</span>
        <span class="grow" />
        <button class="quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <textarea
        value={question}
        placeholder="What barriers reduce HPV vaccination uptake among adolescent girls in low- and middle-income countries?"
        onInput={(event) => setQuestion(event.currentTarget.value)}
        rows={3}
        class="field block"
      />
      <div class="actions">
        <label class="hint">
          Community{" "}
          <select
            class="field"
            value={community}
            onInput={(event) => setCommunity(event.currentTarget.value)}
          >
            {COMMUNITIES.map((option) => (
              <option key={option} value={option}>
                {option.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label class="hint">
          Search{" "}
          <select
            class="field"
            value={mode}
            onInput={(event) => setMode(event.currentTarget.value)}
          >
            <option value="both">by query and concept</option>
            <option value="sparse">by query only</option>
            <option value="taxonomy">by concept only</option>
          </select>
        </label>
      </div>
      <div class="actions">
        <button
          class="btn"
          disabled={!question.trim() || busy}
          onClick={() =>
            onCreate({
              workflow: "evidence_map",
              question: question.trim(),
              community,
              params: { mode },
            })
          }
        >
          Start
        </button>
      </div>
    </>
  );
}
