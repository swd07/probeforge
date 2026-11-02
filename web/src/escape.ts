import { useEffect } from "react";

/** The keydown handler that closes a dialog on Escape (approval cards are left out on purpose: they need an answer). */
export function escapeHandler(onClose: () => void): (e: { key: string }) => void {
  return (e) => {
    if (e.key === "Escape") onClose();
  };
}

/** Close this dialog on Escape while it is open. */
export function useEscape(onClose: () => void): void {
  useEffect(() => {
    const h = escapeHandler(onClose);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
}
