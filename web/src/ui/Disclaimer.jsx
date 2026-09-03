import { useState } from "preact/hooks";
import { repoUrl } from "../repo.js";
import { Warning, Tick } from "./Icons.jsx";

/**
 * Terms of use, shown before a user can reach anything the tool produces and
 * reachable again from the banner afterwards.
 */

const LINKS = {
  repository: repoUrl("destiny"),
  report: null,
};

const Link = ({ to, children }) =>
  to ? (
    <a href={to}>{children}</a>
  ) : (
    <span class="terms-unset">{children}</span>
  );

const SECTIONS = [
  {
    id: "stage",
    heading: "What this is and who it is for",
    body: [
      <>
        <span class="mono">Research Mapper</span> is at{" "}
        <strong>Stage 0: internal development</strong>.
      </>,
      <>
        It has not been tested, benchmarked, or evaluated against anything. Its
        accuracy and completeness are unknown.
      </>,
      <>
        It produces material for building and checking the tool. It is not a
        finding about the evidence.
      </>,
      <>You have access in order to give feedback on the tool.</>,
    ],
  },
  {
    id: "scope",
    heading: "What it searches",
    body: [
      <>
        <Link to={LINKS.repository}>
          The DESTINY community within the broader evidence repository.
        </Link>
      </>,
      <>It screens on titles and abstracts, not the full text.</>,
    ],
  },
  {
    id: "permitted",
    heading: "What you may use the output for",
    body: [<>Building, debugging and evaluating the tool.</>],
  },
  {
    id: "prohibited",
    heading: "What you must not use it for",
    body: [
      <>Any synthesis, briefing, slide or document.</>,
      <>Informing an evidence, research or policy decision.</>,
      <>Producing anything presented as authoritative.</>,
      <>Anything whose subject is the evidence rather than the tool.</>,
      <>Showing an output to anyone outside this group.</>,
    ],
  },
  {
    id: "accountability",
    heading: "What you are accountable for",
    body: [
      <>Adhering to the above terms.</>,
      <>
        <Link to={LINKS.report}>Telling us when something looks wrong.</Link>
      </>,
    ],
  },
];

const Section = ({ heading, body }) => (
  <section class="terms-section">
    <h3 class="terms-heading">{heading}</h3>
    {body.length ? (
      <ul class="terms-list">
        {body.map((point, index) => (
          <li key={index}>{point}</li>
        ))}
      </ul>
    ) : (
      <div class="terms-todo">Copy not yet written.</div>
    )}
  </section>
);

/**
 * `mode` is 'accept' the first time, when the user has to tick and confirm, and
 * 'review' whenever they reopen it from the banner.
 */
export function Disclaimer({ mode = "accept", onAccept, onClose }) {
  const [ticked, setTicked] = useState(false);
  const reviewing = mode === "review";

  return (
    <div
      class="scrim"
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-title"
    >
      <div class="terms">
        <div class="terms-head">
          <Warning />
          <span id="terms-title" class="terms-title">
            Before you use this tool
          </span>
          <span class="grow" />
          <span class="lab">Stage 0 · internal development</span>
        </div>

        <div class="terms-body">
          {SECTIONS.map((section) => (
            <Section key={section.id} {...section} />
          ))}
        </div>

        <div class="terms-foot">
          {reviewing ? (
            <>
              <span class="grow" />
              <button type="button" class="btn" onClick={onClose}>
                Close
              </button>
            </>
          ) : (
            <>
              <label class="terms-tick">
                <input
                  type="checkbox"
                  class="offscreen"
                  checked={ticked}
                  onInput={(event) => setTicked(event.currentTarget.checked)}
                />
                <span class={`box ${ticked ? "on" : ""}`}>
                  {ticked ? <Tick colour="#fff" size={11} /> : null}
                </span>
                <span>I have read and understood the above.</span>
              </label>
              <span class="grow" />
              <button
                type="button"
                class="btn"
                disabled={!ticked}
                onClick={onAccept}
              >
                Continue
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
