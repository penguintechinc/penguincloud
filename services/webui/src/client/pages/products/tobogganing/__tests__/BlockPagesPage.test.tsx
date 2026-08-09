/**
 * Tobogganing SASE Block Pages screen — the only one with writes.
 *
 * Three things are specific to it:
 *
 * 1. **The preview is untrusted HTML.** It is rendered in a fully sandboxed
 *    iframe, never injected into the portal's document. The sandbox attribute
 *    is asserted directly, and asserted to be EMPTY: `allow-scripts` together
 *    with `allow-same-origin` would let the frame remove its own sandbox, so
 *    "has a sandbox attribute" is not a sufficient check.
 * 2. **Edit sends markdown only.** The product's update route reads nothing
 *    else, so a name edit would be accepted by the form and discarded by the
 *    product — with the operator told it saved.
 * 3. **Every write is synchronous.** No operation id, nothing to poll; the
 *    list is invalidated instead.
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const mockIsProductEnabled = jest.fn();
jest.mock("../../../../lib/featureGates", () => ({
  isProductEnabled: (key: string) => mockIsProductEnabled(key),
}));

const mockConnections = jest.fn();
jest.mock("../../../../hooks/useProducts", () => ({
  useProductConnections: () => mockConnections(),
}));

jest.mock("../../../../stores/tenantStore", () => ({
  useTenantStore: (selector: (state: unknown) => unknown) =>
    selector({ currentTenant: { id: 42, name: "Acme" } }),
}));

const tobogganingApi = {
  listBlockPages: jest.fn(),
  createBlockPage: jest.fn(),
  updateBlockPage: jest.fn(),
  previewBlockPage: jest.fn(),
  publishBlockPage: jest.fn(),
};
jest.mock("../../../../api/resources/tobogganing", () => ({ tobogganingApi }));

import BlockPagesPage from "../BlockPagesPage";

function renderPage(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{element}</QueryClientProvider>,
  );
}

const PAGE = {
  id: "3f1b8a2e-9c4d-4f7a-8b21-0d5e6c7a8b90",
  name: "Gambling",
  markdown: "# Blocked\n\nThis site is not permitted.",
  status: "draft",
  version: 2,
  updated_by: "ops@example.com",
  updated_at: "2026-08-09T01:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  mockIsProductEnabled.mockReturnValue(true);
  mockConnections.mockReturnValue({
    data: [{ id: 7, product_type: "tobogganing" }],
    isLoading: false,
  });
  tobogganingApi.listBlockPages.mockResolvedValue([PAGE]);
  tobogganingApi.createBlockPage.mockResolvedValue(PAGE);
  tobogganingApi.updateBlockPage.mockResolvedValue(PAGE);
  tobogganingApi.publishBlockPage.mockResolvedValue({
    ...PAGE,
    status: "published",
  });
  // Resolves to the HTML string: `previewBlockPage` unwraps the `html` key at
  // the boundary so no caller holds an envelope it could default to "".
  tobogganingApi.previewBlockPage.mockResolvedValue("<h1>Blocked</h1>");
});

async function openDrawer() {
  fireEvent.click(
    await screen.findByTestId(`tobogganing-blockpage-open-${PAGE.id}`),
  );
}

describe("gating", () => {
  it("does not fetch when the flag is off", async () => {
    mockIsProductEnabled.mockReturnValue(false);

    renderPage(<BlockPagesPage />);
    await waitFor(() => expect(mockIsProductEnabled).toHaveBeenCalled());

    expect(screen.getByTestId("tobogganing-disabled")).toBeInTheDocument();
    expect(tobogganingApi.listBlockPages).not.toHaveBeenCalled();
  });

  it("does not fetch with no Tobogganing connection", () => {
    mockConnections.mockReturnValue({ data: [], isLoading: false });

    renderPage(<BlockPagesPage />);

    expect(screen.getByTestId("tobogganing-no-connection")).toBeInTheDocument();
    expect(tobogganingApi.listBlockPages).not.toHaveBeenCalled();
  });
});

describe("the page list", () => {
  it("renders the rows the product returned", async () => {
    renderPage(<BlockPagesPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("Gambling")).toBeInTheDocument();
    expect(table.getByText("draft")).toBeInTheDocument();
    expect(table.getByText("2")).toBeInTheDocument();
  });

  it("keeps the markdown source out of the table", async () => {
    // The full page source in a table cell is either truncated into something
    // misleading or wrecks the row height. It belongs in the drawer.
    renderPage(<BlockPagesPage />);

    const table = within(await screen.findByRole("table"));
    expect(table.queryByText(/This site is not permitted/)).toBeNull();
  });

  it("surfaces a decode failure instead of reporting no pages", async () => {
    tobogganingApi.listBlockPages.mockRejectedValue(
      new Error('no "pages" key (got ["items"]) — refusing to report empty'),
    );

    renderPage(<BlockPagesPage />);

    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText(/refusing to report empty/)).toBeInTheDocument();
  });
});

describe("the preview", () => {
  it("renders nothing until the operator asks for one", async () => {
    // Previewing is a POST per page. Rendering one on mount would send a
    // request per row for content nobody asked to see.
    renderPage(<BlockPagesPage />);
    await openDrawer();

    expect(tobogganingApi.previewBlockPage).not.toHaveBeenCalled();
    expect(screen.queryByTestId("tobogganing-preview-frame")).toBeNull();
  });

  it("renders product HTML in a frame that grants nothing back", async () => {
    // The load-bearing security assertion of this screen. The HTML comes from
    // a product the portal proxies to and is authored by whoever can write
    // SASE config for the tenant. Injected into the portal's own document it
    // would run with the operator's session.
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-preview"));

    const frame = await screen.findByTestId("tobogganing-preview-frame");
    expect(frame.tagName).toBe("IFRAME");
    // Empty, NOT merely present. `allow-scripts allow-same-origin` together
    // let framed content remove its own sandbox — strictly worse than none.
    expect(frame).toHaveAttribute("sandbox", "");
    expect(frame).toHaveAttribute("srcdoc", "<h1>Blocked</h1>");
    expect(tobogganingApi.previewBlockPage).toHaveBeenCalledWith(7, PAGE.id);
  });

  it("never injects the HTML into the portal's own document", async () => {
    // Falsifies the assertion above from the other side: a screen that used
    // dangerous inner-HTML would still render an element containing the text,
    // just not inside an iframe. Asserting the markup is absent from the
    // parent document is what distinguishes the two.
    tobogganingApi.previewBlockPage.mockResolvedValue(
      "<h1 data-testid='injected'>pwned</h1>",
    );

    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-preview"));
    await screen.findByTestId("tobogganing-preview-frame");

    expect(screen.queryByTestId("injected")).toBeNull();
    expect(screen.queryByText("pwned")).toBeNull();
  });

  it("shows a preview failure rather than an empty frame", async () => {
    tobogganingApi.previewBlockPage.mockRejectedValue(new Error("boom"));

    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-preview"));

    expect(
      await screen.findByTestId("tobogganing-preview-error"),
    ).toHaveTextContent("boom");
    expect(screen.queryByTestId("tobogganing-preview-frame")).toBeNull();
  });

  it("drops a previous page's render when the drawer closes", async () => {
    // A stale render shown beside a different page's title is a wrong answer
    // presented as a right one.
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-preview"));
    await screen.findByTestId("tobogganing-preview-frame");

    fireEvent.click(screen.getByLabelText(/close/i));
    await openDrawer();

    expect(screen.queryByTestId("tobogganing-preview-frame")).toBeNull();
  });
});

describe("publishing", () => {
  it("confirms before publishing, naming the consequence", async () => {
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-publish"));

    const confirm = screen.getByTestId("tobogganing-blockpage-publish-confirm");
    expect(confirm).toHaveTextContent(/every blocked user/i);
    expect(confirm).toHaveTextContent(/no unpublish route/i);
    expect(tobogganingApi.publishBlockPage).not.toHaveBeenCalled();
  });

  it("publishes only after the confirmation is accepted", async () => {
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-publish"));
    // The drawer's Publish button and the dialog's confirm both read
    // "Publish"; the testid distinguishes the one that actually commits.
    fireEvent.click(
      screen.getByTestId("tobogganing-blockpage-publish-confirm-confirm"),
    );

    await waitFor(() =>
      expect(tobogganingApi.publishBlockPage).toHaveBeenCalledWith(7, PAGE.id),
    );
  });

  it("does not publish when the confirmation is dismissed", async () => {
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-publish"));
    fireEvent.click(
      screen.getByTestId("tobogganing-blockpage-publish-confirm-cancel"),
    );

    expect(tobogganingApi.publishBlockPage).not.toHaveBeenCalled();
  });
});

describe("authoring", () => {
  it("creates a draft from the name and markdown the operator typed", async () => {
    renderPage(<BlockPagesPage />);
    fireEvent.click(await screen.findByTestId("tobogganing-blockpage-create"));

    // Anchored: FormModalBuilder renders a required label as "Name*" with no
    // space, and a loose /name/i would also match nothing else here but the
    // anchoring keeps the failure legible if a field is added.
    fireEvent.change(await screen.findByLabelText(/^Name\*$/), {
      target: { value: "Malware" },
    });
    fireEvent.change(screen.getByLabelText(/^Markdown\*$/), {
      target: { value: "# Nope" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() =>
      expect(tobogganingApi.createBlockPage).toHaveBeenCalledWith(7, {
        name: "Malware",
        markdown: "# Nope",
      }),
    );
  });

  it("offers no status field on create — a new page is always a draft", async () => {
    // Offering one would imply a page can be created published. It cannot:
    // creation always yields a draft and publishing is a separate verb.
    renderPage(<BlockPagesPage />);
    fireEvent.click(await screen.findByTestId("tobogganing-blockpage-create"));
    const name = await screen.findByLabelText(/^Name\*$/);

    // Scoped to the form. An unscoped /status/i also matches the table's
    // "Sort by Status" header button, so the check would pass for the wrong
    // reason — or fail while the form is in fact correct.
    const form = name.closest("form") ?? name.parentElement!;
    expect(within(form).queryByLabelText(/status/i)).toBeNull();
  });

  it("sends only markdown on edit, and offers no name field", async () => {
    // The product's update route reads `markdown` and nothing else. A name
    // field here would be accepted by the form and discarded by the product,
    // with the operator told it saved — the worst of the three behaviours.
    renderPage(<BlockPagesPage />);
    await openDrawer();
    fireEvent.click(screen.getByTestId("tobogganing-blockpage-edit"));

    const markdown = await screen.findByLabelText(/^Markdown\*$/);
    expect(screen.queryByLabelText(/^Name\*?$/)).toBeNull();

    fireEvent.change(markdown, { target: { value: "# Revised" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(tobogganingApi.updateBlockPage).toHaveBeenCalledWith(
        7,
        PAGE.id,
        "# Revised",
      ),
    );
  });

  it("shows the markdown source as text, never as markup", async () => {
    // The source tab is the authored input. Rendering it would be the same
    // injection the preview tab exists to sandbox.
    tobogganingApi.listBlockPages.mockResolvedValue([
      { ...PAGE, markdown: "<script>alert(1)</script>" },
    ]);

    renderPage(<BlockPagesPage />);
    await openDrawer();
    // The drawer renders only the active tab's content.
    fireEvent.click(screen.getByRole("tab", { name: "Markdown" }));

    const source = screen.getByTestId("tobogganing-blockpage-source");
    expect(source.textContent).toBe("<script>alert(1)</script>");
    expect(source.querySelector("script")).toBeNull();
  });
});
