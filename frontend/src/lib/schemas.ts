import { z } from "zod";

/**
 * Wizard "Site & Style" request schema — the frontend mirror of the backend
 * `app/schemas/project.py::GenerateRequest`. Keep the two in lock-step: same
 * field names, types, defaults, and validation rules.
 */

export const programmeFlags = [
  "courtyard",
  "verandah",
  "car_porch_open",
  "pooja",
  "terrace",
  "study",
] as const;

export const gateSides = ["N", "S", "E", "W"] as const;

export const plotTemplates = ["RECT", "L"] as const;

export const siteOptionsSchema = z.object({
  compound_wall: z.boolean().default(true),
  landscaped_setbacks: z.boolean().default(true),
  gate_side: z.enum(gateSides).nullable().default(null),
});

export const generateRequestSchema = z
  .object({
    plot_x_extent: z.number(),
    plot_y_extent: z.number(),
    setback_front: z.number(),
    setback_rear: z.number(),
    setback_left: z.number(),
    setback_right: z.number(),
    num_bedrooms: z.number().int().min(1).max(6),
    toilets: z.number().int().min(1).max(6),
    parking: z.boolean(),
    north_angle_deg: z
      .number()
      .default(0)
      .transform((v) => ((v % 360) + 360) % 360),
    plot_template: z.enum(plotTemplates).default("RECT"),
    notch_width: z.number().nullable().default(null),
    notch_depth: z.number().nullable().default(null),
    style_preset: z.string().nullable().default(null),
    programme: z.set(z.enum(programmeFlags)).default(new Set()),
    site: siteOptionsSchema.default({
      compound_wall: true,
      landscaped_setbacks: true,
      gate_side: null,
    }),
  })
  .superRefine((val, ctx) => {
    if (val.plot_template !== "RECT") {
      if (val.notch_width == null || val.notch_depth == null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["notch_width"],
          message: "notch_width and notch_depth are required for a non-rectangular plot",
        });
      } else if (val.notch_width >= val.plot_x_extent || val.notch_depth >= val.plot_y_extent) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["notch_width"],
          message: "notch is larger than the plot",
        });
      }
    }
    if (val.site.gate_side == null) {
      val.site.gate_side = ["S", "W", "N", "E"][
        Math.floor(((val.north_angle_deg + 45) % 360) / 90)
      ] as (typeof gateSides)[number];
    }
  });

export type GenerateRequest = z.infer<typeof generateRequestSchema>;
