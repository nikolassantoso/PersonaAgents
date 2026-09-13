import type { Persona } from "./data";

export const PERSONA_STORAGE_KEY = "persona-definitions-v1";

export function createLocalPersonaId(): string {
  // getRandomValues also works on self-hosted HTTP origins.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `local_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export function personaNameKey(name: string): string {
  return name.trim().toLowerCase();
}

export function isSavedPersona(value: unknown): value is Persona {
  if (!value || typeof value !== "object") return false;
  const persona = value as Record<string, unknown>;
  return (
    typeof persona.id === "string" &&
    /^[A-Za-z0-9_-]+$/.test(persona.id) &&
    ["name", "description", "system_prompt"].every((key) => {
      const field = persona[key];
      return typeof field === "string" && field.trim().length > 0 &&
        field.trim().length <= (key === "system_prompt" ? 10000 : 100);
    })
  );
}

// Local entries come first; both names and IDs must be unique in the picker.
export function mergePersonas(local: Persona[], server: Persona[]): Persona[] {
  const names = new Set<string>();
  const ids = new Set<string>();
  return [...local, ...server].filter((persona) => {
    const name = personaNameKey(persona.name);
    if (names.has(name) || ids.has(persona.id)) return false;
    names.add(name);
    ids.add(persona.id);
    return true;
  });
}

export function loadSavedPersonas(): Persona[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PERSONA_STORAGE_KEY) || "[]");
    return Array.isArray(value) ? mergePersonas(value.filter(isSavedPersona), []) : [];
  } catch {
    return [];
  }
}

export function savePersonas(personas: Persona[]): void {
  localStorage.setItem(PERSONA_STORAGE_KEY, JSON.stringify(personas.filter(isSavedPersona)));
}
