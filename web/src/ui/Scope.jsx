import { communityLevel, communityName } from "../communities.js";

/**
 * What was searched, stated wherever an output is shown.
 */
export function Scope({ community }) {
  const level = communityLevel(community);
  const searched = level
    ? `${communityName(community)} community at ${level} inclusion`
    : `${communityName(community)} community`;
  return (
    <div class="scope">
      Searched the {searched} in the evidence repository across titles and
      abstracts.
    </div>
  );
}
