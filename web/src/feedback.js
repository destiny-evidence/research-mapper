/**
 * VITE_FEEDBACK_FORM_URL is a Google Forms pre-filled link with the sentinel
 * answers swapped for {url} and {question}.
 */

const TEMPLATE = (import.meta.env?.VITE_FEEDBACK_FORM_URL ?? "").trim();

const FIELDS = ["url", "question"];

/** The form's address with what we know filled in, or null if it is unset. */
export function feedbackUrl(values = {}, template = TEMPLATE) {
  if (!template) return null;
  return FIELDS.reduce(
    (url, field) =>
      url.replaceAll(`{${field}}`, encodeURIComponent(values[field] ?? "")),
    template,
  );
}
