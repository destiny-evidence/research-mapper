import { Fork as ForkIcon } from "./Icons.jsx";

export function ForkButton({ disabled = false, onFork }) {
  return (
    <button
      type="button"
      class="quiet fork-action"
      disabled={disabled}
      onClick={onFork}
    >
      <ForkIcon /> Answer differently in a new session
    </button>
  );
}

export function ForkConfirm({ question, busy, onConfirm, onCancel }) {
  return (
    <div
      class="scrim"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fork-title"
    >
      <div class="terms" style="max-width: 460px;">
        <div class="terms-head">
          <ForkIcon colour="#a8551a" />
          <span id="fork-title" class="terms-title">
            Fork this session
          </span>
        </div>
        <div class="terms-body" style="padding-top: 16px;">
          <p style="font-size: 13px; color: var(--text); line-height: 1.55; margin: 0;">
            This creates a new session from this point, where you can answer the
            below question differently:
          </p>
          <p class="fork-question">{question}</p>
        </div>
        <div class="terms-foot">
          <span class="grow" />
          <button type="button" class="btn plain" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" class="btn" disabled={busy} onClick={onConfirm}>
            Fork
          </button>
        </div>
      </div>
    </div>
  );
}
