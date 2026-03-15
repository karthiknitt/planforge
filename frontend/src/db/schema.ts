import { relations } from "drizzle-orm";
import {
  boolean,
  index,
  integer,
  numeric,
  pgTable,
  real,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";

export const user = pgTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified").default(false).notNull(),
  image: text("image"),
  planTier: text("plan_tier").default("free").notNull(),
  planExpiresAt: timestamp("plan_expires_at"),
  projectCredits: integer("project_credits").default(0).notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at")
    .defaultNow()
    .$onUpdate(() => /* @__PURE__ */ new Date())
    .notNull(),
});

export const session = pgTable(
  "session",
  {
    id: text("id").primaryKey(),
    expiresAt: timestamp("expires_at").notNull(),
    token: text("token").notNull().unique(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
      .$onUpdate(() => /* @__PURE__ */ new Date())
      .notNull(),
    ipAddress: text("ip_address"),
    userAgent: text("user_agent"),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
  },
  (table) => [index("session_userId_idx").on(table.userId)]
);

export const account = pgTable(
  "account",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id").notNull(),
    providerId: text("provider_id").notNull(),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    accessToken: text("access_token"),
    refreshToken: text("refresh_token"),
    idToken: text("id_token"),
    accessTokenExpiresAt: timestamp("access_token_expires_at"),
    refreshTokenExpiresAt: timestamp("refresh_token_expires_at"),
    scope: text("scope"),
    password: text("password"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
      .$onUpdate(() => /* @__PURE__ */ new Date())
      .notNull(),
  },
  (table) => [index("account_userId_idx").on(table.userId)]
);

export const verification = pgTable(
  "verification",
  {
    id: text("id").primaryKey(),
    identifier: text("identifier").notNull(),
    value: text("value").notNull(),
    expiresAt: timestamp("expires_at").notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
      .defaultNow()
      .$onUpdate(() => /* @__PURE__ */ new Date())
      .notNull(),
  },
  (table) => [index("verification_identifier_idx").on(table.identifier)]
);

export const project = pgTable(
  "project",
  {
    id: text("id").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    // Plot dimensions in metres (3 dp for feet→m conversion precision)
    plotLength: numeric("plot_length", { precision: 7, scale: 3 }).notNull(),
    plotWidth: numeric("plot_width", { precision: 7, scale: 3 }).notNull(),
    // Setbacks in metres (3 dp)
    setbackFront: numeric("setback_front", { precision: 6, scale: 3 }).notNull(),
    setbackRear: numeric("setback_rear", { precision: 6, scale: 3 }).notNull(),
    setbackLeft: numeric("setback_left", { precision: 6, scale: 3 }).notNull(),
    setbackRight: numeric("setback_right", { precision: 6, scale: 3 }).notNull(),
    // Orientation — N, S, E, W
    roadSide: text("road_side").notNull(),
    northDirection: text("north_direction").notNull(),
    // Configuration
    numBedrooms: integer("num_bedrooms").notNull(),
    toilets: integer("toilets").notNull(),
    parking: boolean("parking").default(false).notNull(),
    // Extended fields
    city: text("city").default("other").notNull(),
    vastuEnabled: boolean("vastu_enabled").default(false).notNull(),
    roadWidthM: real("road_width_m").default(9.0).notNull(),
    hasPooja: boolean("has_pooja").default(false).notNull(),
    hasStudy: boolean("has_study").default(false).notNull(),
    hasBalcony: boolean("has_balcony").default(false).notNull(),
    // Trapezoid plot support
    plotShape: text("plot_shape").default("rectangular").notNull(),
    plotFrontWidth: numeric("plot_front_width", { precision: 8, scale: 3 }),
    plotRearWidth: numeric("plot_rear_width", { precision: 8, scale: 3 }),
    plotSideOffset: numeric("plot_side_offset", { precision: 8, scale: 3 }),
    // Quadrilateral plot corners — JSON-encoded [[x,y], ...] string
    plotCorners: text("plot_corners"),
    // Multi-floor support (Phase E)
    numFloors: integer("num_floors").default(1).notNull(),
    hasStilt: boolean("has_stilt").default(false).notNull(),
    hasBasement: boolean("has_basement").default(false).notNull(),
    // Municipality / building authority selector (e.g. "Chennai (CMDA)")
    municipality: text("municipality"),
    // Arbitrary room config JSON (Phase C)
    customRoomConfig: text("custom_room_config"),
    // Team assignment — null for solo projects
    teamId: integer("team_id").references(() => team.id, { onDelete: "set null" }),
    // Share link token (public read-only access)
    shareToken: text("share_token").unique(),
    // Client approval workflow — None | "pending" | "approved" | "changes_requested"
    approvalStatus: text("approval_status"),
    approvalNote: text("approval_note"),
    approvalUpdatedAt: timestamp("approval_updated_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
      .defaultNow()
      .$onUpdate(() => new Date())
      .notNull(),
  },
  (table) => [index("project_userId_idx").on(table.userId)]
);

// ── Teams ─────────────────────────────────────────────────────────────────────

export const team = pgTable("teams", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  ownerId: text("owner_id").notNull(),
  planTier: text("plan_tier").default("firm").notNull(),
  planExpiresAt: timestamp("plan_expires_at"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const teamMember = pgTable(
  "team_members",
  {
    id: serial("id").primaryKey(),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id, { onDelete: "cascade" }),
    userId: text("user_id").notNull(),
    role: text("role").default("member").notNull(),
    invitedEmail: text("invited_email"),
    joinedAt: timestamp("joined_at").defaultNow().notNull(),
  },
  (table) => [
    index("team_member_teamId_idx").on(table.teamId),
    index("team_member_userId_idx").on(table.userId),
  ]
);

export const userRelations = relations(user, ({ many }) => ({
  sessions: many(session),
  accounts: many(account),
  projects: many(project),
  teamMemberships: many(teamMember),
}));

export const projectRelations = relations(project, ({ one }) => ({
  user: one(user, {
    fields: [project.userId],
    references: [user.id],
  }),
  team: one(team, {
    fields: [project.teamId],
    references: [team.id],
  }),
}));

export const teamRelations = relations(team, ({ many }) => ({
  members: many(teamMember),
  projects: many(project),
}));

export const teamMemberRelations = relations(teamMember, ({ one }) => ({
  team: one(team, {
    fields: [teamMember.teamId],
    references: [team.id],
  }),
}));

export const sessionRelations = relations(session, ({ one }) => ({
  user: one(user, {
    fields: [session.userId],
    references: [user.id],
  }),
}));

export const accountRelations = relations(account, ({ one }) => ({
  user: one(user, {
    fields: [account.userId],
    references: [user.id],
  }),
}));
