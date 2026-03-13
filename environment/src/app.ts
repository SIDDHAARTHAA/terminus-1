import cors from "cors";
import express from "express";
import morgan from "morgan";

import { authRouter } from "./routes/auth";
import { familyRouter } from "./routes/families";
import { healthRouter } from "./routes/health";

export function createApp() {
  const app = express();

  app.use(cors());
  app.use(express.json());
  app.use(morgan("dev"));

  app.use(healthRouter);
  app.use(authRouter);
  app.use(familyRouter);

  app.use((error: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    res.status(500).json({
      error: "Unhandled server error",
      detail: error.message
    });
  });

  return app;
}
