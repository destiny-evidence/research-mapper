import { Reasoning } from "../Reasoning.jsx";
import { Breakable } from "../text.jsx";

const subtopicCount = (dimension) => {
  const n = (dimension.subtopics ?? []).length;
  return n ? `${n} subtopic${n === 1 ? "" : "s"}` : "";
};

export function Dimensions({ payload }) {
  return (
    <>
      <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px;">
        {payload.dimensions.map((dimension) => (
          <div key={dimension.name}>
            <div style="border-top: 2px solid #3d3b36; padding-top: 8px;">
              <div class="lab">{subtopicCount(dimension)}</div>
              <div style="font-size: 13.5px; color: var(--ink); font-weight: 500; margin-top: 4px;">
                <Breakable>{dimension.name}</Breakable>
              </div>
              <div style="font-size: 11.5px; color: var(--muted); margin-top: 4px; line-height: 1.5;">
                {dimension.description}
              </div>
            </div>
            <div style="margin-top: 9px;">
              {(dimension.subtopics ?? []).map((subtopic) => (
                <div
                  key={subtopic.name}
                  style="font-size: 12.5px; color: var(--ink); padding: 7px 0; border-bottom: 1px solid var(--hair);"
                >
                  <Breakable>{subtopic.name}</Breakable>
                </div>
              ))}
            </div>
            <Reasoning text={payload.subtopic_reasoning?.[dimension.name]} />
          </div>
        ))}
      </div>
    </>
  );
}
