import { z } from "zod";

export const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.coerce.number().int().positive().default(3000),
  WEB_DIST: z.string().default("../web/dist"),

  // Travels to the worker as `--max-megapixels`: the count only means
  // anything after decoding, which happens there.
  MAX_MEGAPIXELS: z.coerce.number().positive().default(100),
  MAX_QUEUE_DEPTH: z.coerce.number().int().positive().default(10),
  JOB_TIMEOUT_SECONDS: z.coerce.number().int().positive().default(120),
  UPLOADS_PER_HOUR: z.coerce.number().int().positive().default(200),

  // `PYTHON_BIN` is a path, not a package.
  PYTHON_BIN: z.string().default("python"),
  WORKER_CWD: z.string().default("../worker"),
});

export type Env = z.infer<typeof envSchema>;

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  const named = parsed.error.issues
    .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
    .join("; ");
  throw new Error(`invalid_environment: ${named}`);
}

export const env = parsed.data;
