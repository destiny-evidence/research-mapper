/**
 * Copying text to the clipboard.
 *
 * navigator.clipboard only exists in a secure context, which the dev server on
 * a bare http:// host is not, so there is a fallback for it to fall back to.
 */
export async function copy(text, target = globalThis) {
  const api = target.navigator?.clipboard;
  if (api) {
    try {
      await api.writeText(text);
      return true;
    } catch {
      // Denied or unavailable: try the old way before giving up.
    }
  }
  return legacyCopy(text, target.document);
}

function legacyCopy(text, document) {
  if (!document?.body) return false;
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  try {
    field.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    field.remove();
  }
}
