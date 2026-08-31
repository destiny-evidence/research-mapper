import { Warning, Info } from "./Icons.jsx";

/** Home bar and persistent disclaimer */
export function Chrome({ onHome, onTerms, children }) {
  return (
    <div class="chrome">
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
        <Warning />
        <span class="lab">Research prototype</span>
        <span>
          This tool has not been evaluated for completeness or accuracy. For
          expert research scoping and exploration only.
        </span>
        <span class="grow" />
        <button type="button" class="banner-info" onClick={onTerms}>
          <Info />
          <span>What this means</span>
        </button>
      </div>
    </div>
  );
}
