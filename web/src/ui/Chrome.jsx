import { Barrier } from './Icons.jsx'

/** Top bar plus the construction banner, which is on every screen by design. */
export function Chrome({ children }) {
  return (
    <>
      <div class="topbar">
        <span class="mark">RM</span>
        <span class="brand">research-mapper</span>
        <span class="grow" />
        {children}
      </div>
      <div class="hazard" />
      <div class="banner">
        <Barrier />
        <span class="lab">Under construction</span>
        <span>Nothing here is checked. Not for decisions.</span>
      </div>
    </>
  )
}
