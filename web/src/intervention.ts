/** ATS: an authorized intervention is under way after the diagnosis when the sources are isolated, or restored with
 * the transfer not yet verified (flow stage 4). Start then needs a second click, so one click cannot end the repair.
 * Before any intervention and after "Transfer verified" (stage 5) Start stays one click. */
export function repairUnderWay(s: {
  status: string;
  done?: { intervention?: boolean } | null;
  panel?: { isolated?: boolean; flow?: number } | null;
}): boolean {
  if (s.status !== "done" || !s.done?.intervention || !s.panel) return false;
  const flow = s.panel.flow ?? 0;
  return flow < 5 && (!!s.panel.isolated || flow === 4);
}
