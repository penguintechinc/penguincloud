import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { createAppQueryClient } from "./lib/queryClient";
import "./index.css";
// Cell-slot extension registrations — side-effect only, must run before the
// first render so `ExtensionCellSlot.tsx`'s registry lookups can resolve.
import "./components/extensions/tobogganing/register";
// Page/detail-tab extension registrations — same side-effect-only contract.
import "./components/extensions/nest/register";

const queryClient = createAppQueryClient();

function render() {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

/**
 * With VITE_MOCKS=true the MSW worker must be running before the first render,
 * or the initial queries race it and hit the network. The mocks module is
 * imported dynamically so it is never pulled into a production bundle.
 */
async function bootstrap() {
  if (import.meta.env.VITE_MOCKS === "true") {
    const { startMocks } = await import("./mocks/browser");
    await startMocks(true);
  }
  render();
}

void bootstrap();
