import { Reasoning } from "../Reasoning.jsx";

export function ConceptFilters({ payload }) {
  return (
    <>
      {payload.groups.map((group) => (
        <div
          key={group.scheme}
          style="padding: 14px 0; border-bottom: 1px solid var(--hair);"
        >
          <div style="display: flex; align-items: baseline; gap: 10px;">
            <span style="font-size: 13.5px; color: var(--ink); font-weight: 500;">
              {group.scheme}
            </span>
            <span class="lab">scheme</span>
          </div>
          <div style="margin-top: 9px;">
            {group.labels.map((label, i) => (
              <div
                key={label}
                style="display: flex; align-items: baseline; gap: 12px; padding: 2px 0;"
              >
                <span style="font-size: 12.5px; color: var(--ink); width: 220px;">
                  {label}
                </span>
                <span class="mono" style="font-size: 11px; color: var(--dim);">
                  {group.concept_local_refs[i]}
                </span>
              </div>
            ))}
          </div>
          <Reasoning text={group.reason} />
        </div>
      ))}
      <div class="note">
        A reference must match at least one concept in each listed scheme.
      </div>
    </>
  );
}
