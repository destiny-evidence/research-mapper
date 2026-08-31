import { Barrier } from "./Icons.jsx";

/** Top bar plus the construction banner, which is on every screen by design.
 * The title is the way back to the session list. */
export function Chrome({ onHome, children }) {
  return (
    <>
      <div class="topbar">
        <button type="button" class="home" onClick={onHome}>
          <span class="mark">RM</span>
          <span class="brand">research-mapper</span>
        </button>
        <span class="grow" />
        {children}
      </div>
      <div class="hazard" />
      <div class="banner">
        <Barrier />
        <span class="lab">Under construction</span>
        <span>This is an experimental feature.</span>
      </div>
    </>
  );
}
