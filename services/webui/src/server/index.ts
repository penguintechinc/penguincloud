import path from "path";
import { fileURLToPath } from "url";
import { createApp, defaultClientDir } from "./app.js";

// Named `moduleFilename`/`moduleDirname` rather than the conventional
// `__filename`/`__dirname` purely for consistency with `app.ts`'s naming;
// this file is never imported by a test (only `app.ts`'s `createApp` is), so
// the ts-jest CJS-wrapper collision that motivated the rename there doesn't
// actually apply here — kept anyway so the two files read the same way.
const moduleFilename = fileURLToPath(import.meta.url);
const moduleDirname = path.dirname(moduleFilename);

// Configuration from environment
const config = {
  port: parseInt(process.env.PORT || "3000", 10),
  flaskApiUrl: process.env.FLASK_API_URL || "http://localhost:5000",
  goApiUrl: process.env.GO_API_URL || "http://localhost:8080",
  nodeEnv: process.env.NODE_ENV || "development",
  clientDir: defaultClientDir(moduleDirname),
};

const app = createApp(config);

// Start server — guarded so importing this module builds `app` without
// binding a real port. Comparing `import.meta.url` against the entry script
// path is the ESM equivalent of the classic `require.main === module` check.
if (import.meta.url === `file://${process.argv[1]}`) {
  app.listen(config.port, () => {
    console.log(`WebUI server running on port ${config.port}`);
    console.log(`Environment: ${config.nodeEnv}`);
    console.log(`Flask API: ${config.flaskApiUrl}`);
    console.log(`Go API: ${config.goApiUrl}`);
  });
}

export { app };
