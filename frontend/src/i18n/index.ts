// i18n VOKARI (Tema 3): una sola lingua app (it|en) guida UI + output AI + template.
// fallbackLng "it" → una chiave mancante mostra l'italiano, mai la chiave grezza.
// Le risorse it.json sono allineate VERBATIM alle stringhe originali dei componenti: con
// lng "it" (default) la UI è identica a prima → i test che asseriscono testo IT restano verdi.
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import it from "./locales/it.json";

export const SUPPORTED_LANGUAGES = ["it", "en"] as const;
export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Etichette nelle lingue native, per il selettore in Impostazioni. */
export const LANGUAGE_LABELS: Record<AppLanguage, string> = {
  it: "Italiano",
  en: "English",
};

void i18n.use(initReactI18next).init({
  resources: { it: { translation: it }, en: { translation: en } },
  lng: "it",
  fallbackLng: "it",
  interpolation: { escapeValue: false }, // React già fa l'escape
  returnNull: false,
});

export default i18n;
