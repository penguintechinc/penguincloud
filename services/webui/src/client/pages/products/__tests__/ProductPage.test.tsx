/**
 * ProductPage is the routed fallback for any connected product without its
 * own manifest-driven screens (`/products/:id`). It used to build its tab
 * list from `schema.sections`, a key `GET /products/{id}/schema` has never
 * returned — the real shape is `{capabilities, schema_status}` — so the
 * capabilities panel silently rendered as an empty shell no matter what the
 * adapter reported. These tests pin down the three honest states that
 * replaced it: a populated capability list, a genuinely-empty/unsupported
 * adapter, and an unreachable adapter — each renders distinguishably, never
 * as a bare empty tab that could pass for "loaded, nothing here."
 */

import { render, screen, waitFor } from "@testing-library/react";
import { useParams } from "react-router";

const api = { get: jest.fn() };
jest.mock("../../../lib/api", () => ({ __esModule: true, default: api }));

import ProductPage from "../ProductPage";

const PRODUCT = {
  id: 7,
  tenant_id: 1,
  product_type: "waddleai",
  display_name: "WaddleAI Prod",
  base_url: "https://waddleai.example.com",
  api_key: "",
  api_secret: "",
  auth_type: "bearer",
  health_endpoint: "/health",
  api_version: "v1",
  is_active: true,
  last_health_check: "2026-08-01T00:00:00Z",
  health_status: "healthy",
  discovered: false,
  metadata_json: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  (useParams as jest.Mock).mockReturnValue({ id: "7" });
});

function mockSchema(response: () => Promise<{ data: unknown }>) {
  api.get.mockImplementation((url: string) => {
    if (url === "/products/7") return Promise.resolve({ data: PRODUCT });
    if (url === "/products/7/schema") return response();
    throw new Error(`unexpected url: ${url}`);
  });
}

test("renders capability names, not clickable tabs, when the adapter reports some", async () => {
  mockSchema(() =>
    Promise.resolve({
      data: { capabilities: ["nodes", "billing"], schema_status: "ok" },
    }),
  );
  render(<ProductPage />);

  await waitFor(() =>
    expect(screen.getByTestId("product-capabilities-list")).toBeInTheDocument(),
  );
  expect(screen.getByText("nodes")).toBeInTheDocument();
  expect(screen.getByText("billing")).toBeInTheDocument();
});

test("shows an honest empty state, not a blank tab, when the adapter has nothing to report", async () => {
  mockSchema(() =>
    Promise.resolve({
      data: { capabilities: [], schema_status: "unsupported" },
    }),
  );
  render(<ProductPage />);

  await waitFor(() =>
    expect(
      screen.getByTestId("product-capabilities-empty"),
    ).toBeInTheDocument(),
  );
  expect(screen.getByText("No management screens yet")).toBeInTheDocument();
});

test("shows a distinct error state, not the empty state, when the adapter is unreachable", async () => {
  mockSchema(() =>
    Promise.reject({
      response: { status: 502, data: { schema_status: "unavailable" } },
    }),
  );
  render(<ProductPage />);

  await waitFor(() =>
    expect(
      screen.getByTestId("product-capabilities-error"),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByTestId("product-capabilities-empty"),
  ).not.toBeInTheDocument();
});

test("renders a not-found message when the product itself fails to load", async () => {
  api.get.mockImplementation((url: string) => {
    if (url === "/products/7") return Promise.reject(new Error("404"));
    return Promise.reject(new Error("404"));
  });
  render(<ProductPage />);

  await waitFor(() =>
    expect(screen.getByText("Product not found.")).toBeInTheDocument(),
  );
});
