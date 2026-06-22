import type { ReactNode } from "react";

// Banner riusabile (round 2 F2/FD14): unifica le 3 copie inline quasi-identiche
// (onboarding Home, warning globale App, nota errore). Stile in vokari.css (.vk-banner).
export function Banner({
  kind = "warn",
  role = "alert",
  children,
  actions,
  onClose,
}: {
  kind?: "warn" | "info";
  role?: "alert" | "note";
  children: ReactNode;
  actions?: ReactNode;   // bottoni a destra (es. "Scarica un modello")
  onClose?: () => void;  // se presente, mostra la × per chiudere
}) {
  return (
    <div className={"vk-banner " + kind} role={role}>
      <span className="bx">{children}</span>
      {actions && <span className="bc">{actions}</span>}
      {onClose && (
        <button className="vk-banner-x" aria-label="Chiudi" onClick={onClose}>×</button>
      )}
    </div>
  );
}
