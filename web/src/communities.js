// The repository communities a session can run against.
const COMMUNITY = {
  destiny_high_recall: {
    name: "DESTINY",
    level: "high recall",
    slug: "destiny",
  },
  destiny_balanced: { name: "DESTINY", level: "balanced", slug: "destiny" },
  destiny_high_precision: {
    name: "DESTINY",
    level: "high precision",
    slug: "destiny",
  },
  hpv: { name: "HPV", level: null, slug: "hpv" },
  esea: { name: "ESEA", level: null, slug: "esea" },
};

/** Selectable communities, newest-session default first. */
export const COMMUNITIES = Object.keys(COMMUNITY);

const describe = (community) => {
  const key = String(community).toLowerCase();
  return COMMUNITY[key] ?? { name: key.toUpperCase(), level: null, slug: key };
};

/** How a community reads on screen, threshold included. */
export const communityLabel = (community) => {
  const { name, level } = describe(community);
  return level ? `${name} (${level})` : name;
};

/** A community's name, without its inclusion threshold. */
export const communityName = (community) => describe(community).name;

/** A community's inclusion threshold, or null if it has only the one. */
export const communityLevel = (community) => describe(community).level;

/** The evidence repository path segment a community's references live under. */
export const communitySlug = (community) => describe(community).slug;
