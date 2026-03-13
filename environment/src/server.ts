import { createServer } from "http";

import { createApp } from "./app";
import { config } from "./lib/config";

const app = createApp();
const server = createServer(app);

server.listen(config.PORT, () => {
  console.log(`familyhub-api listening on http://127.0.0.1:${config.PORT}`);
});

function shutdown() {
  server.close(() => {
    process.exit(0);
  });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
