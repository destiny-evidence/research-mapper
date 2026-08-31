import { Warning, Info } from "./Icons.jsx";
import { profile, logout } from "../auth.js";

/** User signed-in hint */
function User() {
  const user = profile();
  const label = user && (user.name || user.email);
  if (!label) return null;
  return (
    <div class="who">
      <span class="who-name" title={user.email !== label ? user.email : null}>
        {label}
      </span>
      <button type="button" class="signout" onClick={logout}>
        Sign out
      </button>
    </div>
  );
}

/** Navbar and disclaimer. */
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
        <User />
      </div>
      <div class="hazard" />
      <div class="banner">
        <Warning />
        <span class="lab">Internal prototype</span>
        <span>
          Not evaluated for completeness or accuracy. For internal development
          and testing only.
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
