import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { PERSONA_STORAGE_KEY, loadSavedPersonas, mergePersonas, savePersonas } from "../src/personaStorage.ts";

const persona = (id, name, prompt = "Local instructions") => ({
  id, name, description: "A visitor", system_prompt: prompt,
});

beforeEach(() => {
  const values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
  });
});

test("local definitions survive reload and an empty server registry", () => {
  const local = persona("local_123", "My persona");
  savePersonas([local]);
  assert.deepEqual(mergePersonas(loadSavedPersonas(), []), [local]);
});

test("local names win regardless of case, spaces, or different server IDs", () => {
  const local = persona("local_123", "  Shopper  ");
  const other = persona("other", "Other");
  assert.deepEqual(mergePersonas([local], [persona("server_123", "SHOPPER", "Server instructions"), other]), [local, other]);
});

test("an empty browser loads server definitions and saves them for later", () => {
  const server = [persona("server_123", "Shopper")];
  const merged = mergePersonas(loadSavedPersonas(), server);
  savePersonas(merged);
  assert.deepEqual(loadSavedPersonas(), server);
});

test("an ID collision also preserves the local definition", () => {
  const local = persona("shared", "Local name");
  assert.deepEqual(mergePersonas([local], [persona("shared", "Server name")]), [local]);
});

test("a newly created same-name persona replaces the saved version", () => {
  const replacement = persona("shared", "Shopper", "Updated instructions");
  savePersonas(mergePersonas([replacement], [persona("shared", "Shopper")]));
  assert.deepEqual(loadSavedPersonas(), [replacement]);
});

test("malformed storage and demo placeholders do not override server data", () => {
  localStorage.setItem(PERSONA_STORAGE_KEY, "not JSON");
  assert.deepEqual(loadSavedPersonas(), []);
  localStorage.setItem(PERSONA_STORAGE_KEY, JSON.stringify([null, {}, persona("../bad", "Invalid"), persona("demo", "Demo", "")]));
  assert.deepEqual(loadSavedPersonas(), []);
  savePersonas([persona("demo", "Demo", "")]);
  assert.deepEqual(loadSavedPersonas(), []);
});
