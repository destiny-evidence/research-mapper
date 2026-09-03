/** Links into the evidence repository's web UI. */

const ENV = import.meta.env?.VITE_DESTINY_ENV ?? "production";

const SEGMENT = { production: null, staging: "staging", development: "dev" };
const segment = ENV in SEGMENT ? SEGMENT[ENV] : ENV;

const HOST = segment
  ? `data.${segment}.evidence-repository.org`
  : "data.evidence-repository.org";

export const repoUrl = (...segments) => `https://${HOST}/${segments.join("/")}`;

/** One reference, in the community that gathered it. */
export const referenceUrl = (community, destinyId) =>
  repoUrl(String(community).toLowerCase(), "references", destinyId);
