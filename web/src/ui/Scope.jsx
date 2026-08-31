/**
 * What was searched, stated wherever an output is shown rather than left to a
 * separate document. Deliberately says what is *not* covered — a reader who
 * only sees "HPV" has no way to know this is one repository, title and abstract
 * only, and nothing else.
 */
export function Scope({ community }) {
  return (
    <div class="scope">
      Searched the {community.toUpperCase()} repository only, screening titles and abstracts.
      No external databases or grey literature.
    </div>
  )
}
