import { type ReactNode, useState } from "react";

/** A section that collapses to one line (closed by default); its content stays mounted, so its inputs keep state. */
export function Fold({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className={`fold ${open ? "open" : ""}`}>
      <button className="fold-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>{title}</span>
        <span className="chevron">{open ? "\u25b4" : "\u25be"}</span>
      </button>
      <div className="fold-body" hidden={!open}>{children}</div>
    </section>
  );
}
