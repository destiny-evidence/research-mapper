import { useEffect, useRef, useState } from "preact/hooks";
import { copy } from "../clipboard.js";
import { Link, Tick } from "./Icons.jsx";

const SETTLE_MS = 2600;

/**
 * Copies the address of whatever is on screen. The button says which address
 * before the click and that it went before it settles back, so a silent
 * clipboard is never mistaken for a copied one.
 */
export function CopyLink({ href = null, label = "Copy link" }) {
  const [state, setState] = useState("idle");
  const timer = useRef(null);
  const url = href ?? window.location.href;

  useEffect(() => () => clearTimeout(timer.current), []);

  const onClick = async () => {
    const ok = await copy(url);
    setState(ok ? "done" : "failed");
    clearTimeout(timer.current);
    if (ok) timer.current = setTimeout(() => setState("idle"), SETTLE_MS);
  };

  return (
    <div class="copy-link">
      <button
        type="button"
        class="quiet"
        onClick={onClick}
        title={`Copy ${url}`}
      >
        {state === "done" ? <Tick colour="#5f7d69" /> : <Link />}
        <span aria-live="polite">
          {state === "done" ? "Link copied" : label}
        </span>
      </button>
      {/* Nothing was copied, so the address has to be reachable by hand. */}
      {state === "failed" ? (
        <input
          class="field copy-url mono"
          readOnly
          value={url}
          onFocus={(event) => event.currentTarget.select()}
          ref={(node) => node?.select()}
        />
      ) : null}
    </div>
  );
}
