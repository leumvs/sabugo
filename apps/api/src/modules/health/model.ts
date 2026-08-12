import { z } from "zod";

export const HealthSchema = z
  .object({
    status: z.literal("ok"),
  })
  .openapi("Health");
