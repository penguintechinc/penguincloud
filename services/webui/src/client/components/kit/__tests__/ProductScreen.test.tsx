/**
 * `ProductScreen` — the generic flag/connection/header shell every product
 * screen (`GoughScreen`, `NestScreen`, `TobogganingScreen`) is built on.
 *
 * The gates are the point of this file. A product screen must render
 * nothing product-shaped when the feature flag is off OR the tenant has no
 * connection for that product, and both conditions live in this one shared
 * shell precisely so a new product cannot ship a screen with one of them
 * missing.
 */

import { render, screen } from "@testing-library/react";
import { ProductScreen } from "../ProductScreen";

const mockUseProductEnabled = jest.fn();
jest.mock("../../../lib/featureGates", () => ({
  useProductEnabled: (key: string) => mockUseProductEnabled(key),
}));

beforeEach(() => {
  jest.clearAllMocks();
});

describe("flag gate", () => {
  it("renders the disabled empty state and nothing product-shaped when the flag is off", () => {
    mockUseProductEnabled.mockReturnValue(false);

    render(
      <ProductScreen
        productType="gough"
        productLabel="Gough"
        title="Nodes"
        description="desc"
        productId={7}
        isConnectionLoading={false}
        noConnectionReason="manage its fleet."
      >
        <div data-testid="child">child</div>
      </ProductScreen>,
    );

    expect(screen.getByTestId("gough-disabled")).toBeInTheDocument();
    expect(screen.queryByTestId("gough-screen")).not.toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
    expect(screen.getByText("Gough is not enabled")).toBeInTheDocument();
  });

  // The test id and flag key are both derived from `productType`. A shell
  // that hardcoded "gough" anywhere in the gate would fail this the moment a
  // second product used it — which is exactly the regression this proves
  // against, by injection: swap the productType and everything must follow.
  it("keys the flag lookup and the disabled test id off productType, not a hardcoded product", () => {
    mockUseProductEnabled.mockReturnValue(false);

    render(
      <ProductScreen
        productType="nest"
        productLabel="Nest"
        title="Databases"
        description="desc"
        productId={undefined}
        isConnectionLoading={false}
        noConnectionReason="manage its data resources."
      >
        <div>child</div>
      </ProductScreen>,
    );

    expect(mockUseProductEnabled).toHaveBeenCalledWith("nest");
    expect(screen.getByTestId("nest-disabled")).toBeInTheDocument();
    expect(screen.queryByTestId("gough-disabled")).not.toBeInTheDocument();
  });
});

describe("connection gate", () => {
  beforeEach(() => {
    mockUseProductEnabled.mockReturnValue(true);
  });

  it("shows a loading placeholder while the connection list is loading", () => {
    render(
      <ProductScreen
        productType="gough"
        productLabel="Gough"
        title="Nodes"
        description="desc"
        productId={undefined}
        isConnectionLoading
        noConnectionReason="manage its fleet."
      >
        <div data-testid="child">child</div>
      </ProductScreen>,
    );

    expect(screen.getByTestId("gough-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("renders a no-connection empty state built from productLabel and noConnectionReason", () => {
    render(
      <ProductScreen
        productType="gough"
        productLabel="Gough"
        title="Nodes"
        description="desc"
        productId={undefined}
        isConnectionLoading={false}
        noConnectionReason="manage its fleet."
      >
        <div data-testid="child">child</div>
      </ProductScreen>,
    );

    expect(screen.getByTestId("gough-no-connection")).toBeInTheDocument();
    expect(screen.getByText("No Gough connection")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Register a Gough connection for this tenant to manage its fleet.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });
});

describe("content", () => {
  it("renders the header and children once both gates pass", () => {
    mockUseProductEnabled.mockReturnValue(true);

    render(
      <ProductScreen
        productType="gough"
        productLabel="Gough"
        title="Nodes"
        description="Physical machines under Gough management."
        productId={7}
        isConnectionLoading={false}
        noConnectionReason="manage its fleet."
      >
        <div data-testid="child">child content</div>
      </ProductScreen>,
    );

    const shell = screen.getByTestId("gough-screen");
    expect(shell).toBeInTheDocument();
    expect(screen.getByText("Nodes")).toBeInTheDocument();
    expect(
      screen.getByText("Physical machines under Gough management."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.queryByTestId("gough-disabled")).not.toBeInTheDocument();
    expect(screen.queryByTestId("gough-no-connection")).not.toBeInTheDocument();
  });
});
