import type { Language } from "@/components/types";

const LANG_STORAGE_KEY = "rv-lang";
export const LANG_EVENT = "rv:language";

export function readStoredLang(): Language {
  if (typeof window === "undefined") return "es";
  const stored = window.localStorage.getItem(LANG_STORAGE_KEY);
  if (stored === "es" || stored === "en") return stored;
  return "es";
}

export function persistLang(language: Language) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LANG_STORAGE_KEY, language);
  window.dispatchEvent(new CustomEvent(LANG_EVENT, { detail: language }));
}
