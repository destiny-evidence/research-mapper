import { useState } from 'preact/hooks'
import { Warning, Tick } from './Icons.jsx'

/**
 * Terms of use, shown before a user can reach anything the tool produces and
 * reachable again from the banner afterwards.
 *
 * Written for Stage 0 (internal development): the only condition met is that
 * the tool produces coherent outputs. If the stage moves, the header label and
 * the stage, permitted, prohibited and accountability sections all move with
 * it — Table 2 of the framework is the source for every one of them. Stage 1
 * in particular widens the audience to research partners and adds two standing
 * obligations (a named researcher per use, structured feedback after each
 * use) that do not exist yet.
 *
 * COPY IS NOT WRITTEN. Each section below carries the points it has to cover
 * and why; someone who can speak for the project fills in `body`. Sections with
 * an empty body render as a visible TODO rather than silently disappearing, so
 * an unfinished disclaimer cannot ship looking finished.
 */
const SECTIONS = [
  {
    id: 'stage',
    heading: 'What this is and who it is for',
    // - Stage 0, internal development, per the stage-gated framework
    // - the only condition met is that it produces coherent outputs; there has
    //   been no testing, no benchmarking, no evaluation of any kind
    // - so accuracy and completeness are unknown quantities, not merely
    //   imperfect ones
    // - the audience is the development team. Anyone else reading this is
    //   outside the intended audience and should say so
    // - the outputs are material for building and testing the tool, not
    //   findings about the evidence
    body: [],
  },
  {
    id: 'scope',
    heading: 'What it searches',
    // - one DESTINY community repository per session, and nothing else
    // - name what is NOT searched: PubMed, Embase, Cochrane, grey literature,
    //   anything outside the repository
    // - screening happens on title and abstract only, never full text
    // - the repository's own coverage, inclusion criteria and gaps are a
    //   separate document — link it once it exists
    body: [],
  },
  {
    id: 'permitted',
    heading: 'What you may use the output for',
    // Table 2, Stage 0: internal development and testing only.
    // - building, debugging and evaluating the tool itself
    // - judging whether a step behaves sensibly, so the next gate has evidence
    // - nothing whose subject is the evidence rather than the tool
    body: [],
  },
  {
    id: 'prohibited',
    heading: 'What you must not use it for',
    // Table 2, Stage 0 is a single sweeping line: anything beyond internal
    // development. Worth spelling out what that rules out in practice, because
    // "internal" gets stretched:
    // - showing an output to anyone outside the development team, including
    //   colleagues on the wider project and stakeholders asking for a preview
    // - any synthesis, briefing, slide or document, however caveated
    // - informing a decision, including a decision about what to research next
    // And the three from the gate review, section 1.2, which stand at every
    // stage:
    // - primary search or screening for any synthesis that will be published
    //   or used to inform a decision
    // - clinical, legal or regulatory decisions where completeness of the
    //   evidence base is safety-critical
    // - use by anyone without domain expertise and evidence synthesis
    //   training, to produce anything presented as authoritative
    body: [],
  },
  {
    id: 'rules',
    heading: 'Five rules that always apply',
    // Verbatim from the gate review, section 1.2:
    // - no claims of comprehensiveness or completeness
    // - no claims of absence: nothing found is not the same as nothing exists
    // - no conclusions from the map alone: it describes where evidence sits,
    //   not what it says, how good it is, or how certain it is
    // - no autonomous decisions: the tool identifies patterns, people decide
    // - no autonomous vocabulary governance: it proposes, humans approve
    body: [],
  },
  {
    id: 'accountability',
    heading: 'What you are accountable for',
    // Stage 0 governance is the development team, and rollback conditions are
    // "not applicable" — so the obligations here are ordinary care, not the
    // formal ones Stage 1 introduces.
    // - every approval step is yours and is recorded against the session;
    //   approving a suggestion you have not read is still your decision
    // - an output that leaves the team is your doing, not the tool's
    // - what breaks here is what the next gate is decided on, so say when
    //   something looks wrong; name where that goes
    body: [],
  },
]

const Section = ({ heading, body }) => (
  <section class="terms-section">
    <h3 class="terms-heading">{heading}</h3>
    {body.length ? (
      <ul class="terms-list">
        {body.map((point, index) => <li key={index}>{point}</li>)}
      </ul>
    ) : (
      <div class="terms-todo">Copy not yet written. See the notes in Disclaimer.jsx.</div>
    )}
  </section>
)

/**
 * `mode` is 'accept' the first time, when the user has to tick and confirm, and
 * 'review' whenever they reopen it from the banner — reading the terms again is
 * not a new decision and should not be staged as one.
 */
export function Disclaimer({ mode = 'accept', onAccept, onClose }) {
  const [ticked, setTicked] = useState(false)
  const reviewing = mode === 'review'

  return (
    <div class="scrim" role="dialog" aria-modal="true" aria-labelledby="terms-title">
      <div class="terms">
        <div class="terms-head">
          <Warning />
          <span id="terms-title" class="terms-title">Before you use this tool</span>
          <span class="grow" />
          <span class="lab">Stage 0 · internal development</span>
        </div>

        <div class="terms-body">
          {SECTIONS.map((section) => <Section key={section.id} {...section} />)}
        </div>

        <div class="terms-foot">
          {reviewing ? (
            <>
              <span class="grow" />
              <button type="button" class="btn" onClick={onClose}>Close</button>
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
                <span class={`box ${ticked ? 'on' : ''}`}>
                  {ticked ? <Tick colour="#fff" size={11} /> : null}
                </span>
                {/* TODO copy: one sentence, first person, naming what is being
                    agreed to — not "I have read the above". */}
                <span>I have read and understood the above.</span>
              </label>
              <span class="grow" />
              <button type="button" class="btn" disabled={!ticked} onClick={onAccept}>Continue</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
