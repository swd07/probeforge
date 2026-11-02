import { labelIds } from "../labels";
import { useEscape } from "../escape";
import type { AtsMeta } from "../types";

/** The never-tier attempts counted from the committed runs, with the source; "" when the server has no count. */
export function neverText(counts: AtsMeta["never_attempts"]): string {
  const rows = Object.entries(counts ?? {});
  if (!rows.length) return "";
  const parts = rows.map(([runner, c]) => `${runner} ${c.never} in ${c.runs} runs`);
  return `Never-tier attempts in the committed runs: ${parts.join(", ")} (scripts/count_never_attempts.py over results/runs, from the policy tier logged with every step).`;
}

/** The agent action limits, generated from the ATS policy code (the same table as docs/ATS_MODEL.md). */
export function LimitsModal({ meta, onClose }: { meta: AtsMeta | null; onClose: () => void }) {
  useEscape(onClose);
  if (!meta) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal limits-modal" role="dialog" aria-label="Agent action limits" onClick={(e) => e.stopPropagation()}>
        <div className="result-head">
          <div>
            <div className="modal-kicker">Enforced in code, not in the prompt</div>
            <h2>Agent action limits (from the policy code)</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close">{"\u00d7"}</button>
        </div>
      <table className="limits-table">
        <tbody>
          {meta.limits.map((l, i) => (
            <tr key={i} className={`tier-${l.tier.replace(" ", "-")}`}>
              <td>
                {labelIds(l.action).map((p, j) =>
                  p.label ? <span key={j}><code>{p.text}</code> <span className="id-label">({p.label})</span></span> : <span key={j}>{p.text}</span>)}
              </td>
              <td className="tier">{l.tier}</td>
              <td>{l.condition}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {neverText(meta.never_attempts) && <p className="muted never-count">{neverText(meta.never_attempts)}</p>}
      </div>
    </div>
  );
}
