import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 10, // 10 minutes (formerly cacheTime)
      retry: false,
    },
  },
});

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
