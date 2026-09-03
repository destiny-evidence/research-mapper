import { Fragment } from "preact";

/**
 * Compound labels like "Channel/Medium", which seem to be favoured by the LLM,
 * are one long word, so they overflow rather than wrap. This lets them wrap.
 */
export function Breakable({ children }) {
  const parts = String(children ?? "").split("/");
  if (parts.length === 1) return children ?? null;
  return parts.map((part, index) => (
    <Fragment key={index}>
      {index < parts.length - 1 ? (
        <>
          {part}/<wbr />
        </>
      ) : (
        part
      )}
    </Fragment>
  ));
}
