/**
 * What was searched, stated wherever an output is shown.
 */
export function Scope({ community }) {
  return (
    <div class="scope">
      Searched the {community.toUpperCase()} repository only, screening titles
      and abstracts.
    </div>
  );
}
