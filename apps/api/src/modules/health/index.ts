import { createRoute, OpenAPIHono } from "@hono/zod-openapi";
import { HealthSchema } from "./model";

const healthRoute = createRoute({
  method: "get",
  path: "/",
  tags: ["infra"],
  summary: "Api Health Check",
  responses: {
    200: {
      content: { "application/json": { schema: HealthSchema } },
      description: "returns ok if the api is healthy",
    },
  },
});

export const createHealthRoutes = () => {
  const routes = new OpenAPIHono();

  routes.openapi(healthRoute, (c) => c.json({ status: "ok" as const }));

  return routes;
};
