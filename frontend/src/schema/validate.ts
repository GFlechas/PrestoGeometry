import Ajv, { type ValidateFunction } from "ajv";
import type { Floorplan } from "./types";

let validator: ValidateFunction | null = null;
let loadingPromise: Promise<ValidateFunction> | null = null;

async function fetchSchema(): Promise<unknown> {
  const res = await fetch("/api/schema");
  if (!res.ok) {
    throw new Error(`failed to fetch /api/schema: ${res.status}`);
  }
  return res.json();
}

/**
 * Load and compile the floorspace JSON schema (Draft-04) the first time it's
 * requested; cache the validator after that.
 */
export async function getValidator(): Promise<ValidateFunction> {
  if (validator) return validator;
  if (!loadingPromise) {
    loadingPromise = (async () => {
      const schema = (await fetchSchema()) as Record<string, unknown>;
      // Ajv defaults target Draft-07; floorspace uses Draft-04. Strip the
      // `$schema` keyword so Ajv doesn't try to look it up over the network,
      // and disable strict mode to tolerate non-standard keywords like
      // `si_units` / `ip_units` that the schema uses for documentation.
      const { $schema, ...rest } = schema;
      void $schema;
      const ajv = new Ajv({
        strict: false,
        allErrors: true,
        validateFormats: false,
      });
      validator = ajv.compile(rest);
      return validator;
    })();
  }
  return loadingPromise;
}

export interface ValidationResult {
  valid: boolean;
  errors: { path: string; message: string }[];
}

export async function validateFloorplan(data: unknown): Promise<ValidationResult> {
  const v = await getValidator();
  const ok = v(data);
  if (ok) return { valid: true, errors: [] };
  const errors = (v.errors ?? []).map((e) => ({
    path: e.instancePath || "/",
    message: e.message ?? "unknown",
  }));
  return { valid: false, errors };
}

export type { Floorplan };
