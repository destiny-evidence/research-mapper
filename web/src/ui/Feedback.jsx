import { feedbackUrl } from "../feedback.js";
import { Flag } from "./Icons.jsx";

/** Pinned to the corner of a session, carrying that session with it. */
export function FeedbackTab({ question = "" }) {
  const href = feedbackUrl({ url: window.location.href, question });
  if (!href) return null;
  return (
    <a
      class="feedback-tab"
      href={href}
      target="_blank"
      rel="noreferrer"
      title="Opens a form, with this session's link and question filled in"
    >
      <Flag size={15} />
      <span>Feedback</span>
    </a>
  );
}
