/**
 * What was searched, stated wherever an output is shown.
 */
export function Scope({ community }) {
  return (
    <div class="scope">
      Searched the {community.toUpperCase()} repository only across titles and
      abstracts.
    </div>
  );
}
