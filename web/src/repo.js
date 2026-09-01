/** Links into the evidence repository's web UI. */

const ENV = import.meta.env?.VITE_DESTINY_ENV ?? "production";

const HOST =
  ENV === "production"
    ? "data.evidence-repository.org"
    : `data.${ENV}.evidence-repository.org`;

export const repoUrl = (...segments) => `https://${HOST}/${segments.join("/")}`;

/** One reference, in the community that gathered it. */
export const referenceUrl = (community, destinyId) =>
  repoUrl(String(community).toLowerCase(), "references", destinyId);
