import { z } from "@hono/zod-openapi";

/** snake_case while the rest of the JSON is camelCase: these are the
 *  reference tool's own names, so a published configuration reproduces here
 *  without translation. */
export const ParamsSchema = z
  .object({
    mode: z.enum(["broken_roots", "whole_root"]).default("broken_roots"),
    threshold_method: z.enum(["manual", "otsu"]).default("manual"),
    threshold_value: z.number().int().min(0).max(255).default(200),
    invert_image: z.boolean().default(false),
    keep_largest: z.boolean().default(true),
    filter_background_noise: z.boolean().default(false),
    max_background_noise_mm2: z.number().positive().default(1.0),
    filter_foreground_noise: z.boolean().default(false),
    max_foreground_noise_mm2: z.number().positive().default(1.0),
    enable_edge_smoothing: z.boolean().default(false),
    edge_smoothing_threshold: z.number().positive().default(2.0),
    enable_root_pruning: z.boolean().default(false),
    root_pruning_threshold: z.number().int().nonnegative().default(5),
    // Inner boundaries: `[2, 5]` is three classes, and at most 11 of them.
    diameter_ranges_mm: z.array(z.number().positive()).min(1).max(11).default([2.0, 5.0]),
    // These change only the feature image, never a number.
    show_medial_axis: z.boolean().default(true),
    medial_axis_width: z.number().int().min(1).max(20).default(3),
    show_medial_axis_diameter: z.boolean().default(true),
    show_contours: z.boolean().default(false),
    contour_width: z.number().int().min(1).max(20).default(1),
    show_convex_hull: z.boolean().default(false),
    show_holes: z.boolean().default(false),
    show_dist_map: z.boolean().default(false),
  })
  .refine(
    (params) =>
      params.diameter_ranges_mm.every(
        (value, index) => index === 0 || value > (params.diameter_ranges_mm[index - 1] as number),
      ),
    { error: "diameter_ranges_must_be_strictly_increasing", path: ["diameter_ranges_mm"] },
  );

export type AnalysisParams = z.infer<typeof ParamsSchema>;

export const RoiSchema = z.object({
  name: z.string().min(1).max(64),
  x: z.number().int().nonnegative(),
  y: z.number().int().nonnegative(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
});

export type Roi = z.infer<typeof RoiSchema>;

/** Ten per analysis, and the worker refuses the eleventh as well. */
export const RoisSchema = z.array(RoiSchema).max(10);

/** The hard limits only; warning about an unusual DPI is the client's job. */
export const DpiSchema = z.coerce.number().min(50).max(4800);

export const AcceptedSchema = z.object({
  id: z.uuid(),
  status: z.literal("pending"),
  queuePosition: z.number().int().nonnegative(),
  queuedAt: z.iso.datetime(),
});

export const ErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
});

/**
 * A raw OpenAPI schema and not a Zod one: `@hono/zod-openapi` attaches a
 * `zValidator("form", …)` to any Zod body schema, and that validator calls
 * `c.req.parseBody()`, which reads the whole request into memory. A plain
 * object is documented and skipped (`if (!isZod(schema)) continue`).
 */
export const UploadBodySchema = {
  type: "object",
  required: ["image", "dpi"] as string[],
  properties: {
    dpi: { type: "string", example: "600", description: "in [50, 4800]" },
    params: { type: "string", description: "JSON object of analysis parameters" },
    rois: { type: "string", description: "JSON array of rectangles, at most 10" },
    image: { type: "string", format: "binary" },
  },
  description: "Send dpi, params and rois before image — see the route description.",
} as const;
