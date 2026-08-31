import { useState } from 'preact/hooks'
import { Warning, Tick } from './Icons.jsx'

/**
 * Terms of use, shown before a user can reach anything the tool produces and
 * reachable again from the banner afterwards.
 *
 * Written for Stage 1 (controlled research use): basic testing done, formal
 * benchmarking not. If the stage moves, the header label, the permitted and
 * prohibited sections, and the accountability obligations all move with it —
 * Table 2 of the framework is the source for all four.
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
    // - Stage 1, controlled research use, per the stage-gated framework
    // - basic testing done and limitations documented; NOT formally
    //   benchmarked — that is Stage 2's condition, not this one
    // - so accuracy and completeness are still unknown quantities, not merely
    //   imperfect ones
    // - it is for research partners with domain expertise, and expert
    //   judgement at the approval points is what makes the output usable
    // - the outputs are a starting point for expert work, not a result
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
    // - say what supplementary searching is recommended, specifically, rather
    //   than a general caution that it may not find everything (P2.5)
    body: [],
  },
  {
    id: 'permitted',
    heading: 'What you may use the output for',
    // Table 2, Stage 1: expert research scoping and exploration only.
    // - orienting yourself in an unfamiliar area
    // - generating candidate search strings you will review and run yourself
    // - drafting eligibility criteria you will revise
    // - forming hypotheses about where evidence may be concentrated
    body: [],
  },
  {
    id: 'prohibited',
    heading: 'What you must not use it for',
    // Table 2, Stage 1 — outputs cannot be used for:
    // - policy decisions
    // - systematic reviews
    // - the sole evidence base for any decision
    // - sharing beyond research partners
    // And the three from the gate review, section 1.2, which still stand:
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
    // Stage 1 governance is "named researcher for each use; structured
    // feedback required after each use", so both are obligations, not asks:
    // - you are the named researcher for every session you start
    // - structured feedback after each use is required, not optional — say
    //   how it is given and to whom
    // - every approval step is yours and is recorded against the session;
    //   approving a suggestion you have not read is still your decision
    // - if you share an output the caveats travel with it, or you removed them
    // - name who to contact when the tool produces something wrong, and say
    //   that reporting it is expected (it is also a rollback trigger)
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
          <span class="lab">Stage 1 · controlled research use</span>
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
