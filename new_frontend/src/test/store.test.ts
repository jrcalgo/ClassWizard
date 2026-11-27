import { MAX_CAREERS } from "@/lib/plan";
import { usePlanStore } from "@/state/planStore";

describe("career selection", () => {
  beforeEach(() => usePlanStore.setState({ selectedCareers: {} }));

  it(`caps the selection at ${MAX_CAREERS}`, () => {
    const { toggleCareer } = usePlanStore.getState();
    for (let i = 0; i < MAX_CAREERS + 2; i++) toggleCareer({ soc_code: `c${i}`, title: `Career ${i}` }, true);
    expect(Object.keys(usePlanStore.getState().selectedCareers)).toHaveLength(MAX_CAREERS);
    toggleCareer({ soc_code: "c0", title: "Career 0" }, false);
    expect(Object.keys(usePlanStore.getState().selectedCareers)).toHaveLength(MAX_CAREERS - 1);
  });

  it("clearAudit drops everything that depended on the audit", () => {
    usePlanStore.setState({ sessionId: "a".repeat(32), messages: [{ role: "assistant", content: "hi" }] });
    usePlanStore.getState().clearAudit();
    const state = usePlanStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.plan).toBeNull();
    expect(state.messages).toEqual([]);
  });
});
