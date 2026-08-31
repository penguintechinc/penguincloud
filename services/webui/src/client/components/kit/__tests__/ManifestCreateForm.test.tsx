/**
 * `ManifestCreateForm` — the manifest's `create: FormSpec` bound to
 * react-libs' real `FormBuilder` (`mode="modal"`), submitting through the
 * generic typed create route with `field_aliases` applied.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createAppQueryClient } from "../../../lib/queryClient";
import { ManifestCreateForm } from "../ManifestCreateForm";
import api from "../../../lib/api";
import type { ResourceDescriptor } from "../manifestTypes";

jest.mock("../../../lib/api", () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

const mockedApi = api as unknown as { post: jest.Mock };

function resource(
  overrides: Partial<ResourceDescriptor> = {},
): ResourceDescriptor {
  return {
    kind: "biomes",
    label: "Biome",
    plural_label: "Biomes",
    id_field: "id",
    name_field: "name",
    transport: "typed",
    columns: [],
    empty_state: "empty",
    error_state: "error",
    list: null,
    item_path: null,
    detail: { tabs: [] },
    actions: [],
    create: null,
    delete: null,
    relationships: [],
    ...overrides,
  };
}

function renderForm(res: ResourceDescriptor) {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <ManifestCreateForm
        productType="gough"
        tenantId={42}
        productId={7}
        resource={res}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

it("renders nothing when the resource declares no create", () => {
  const { container } = renderForm(resource({ create: null }));
  expect(container).toBeEmptyDOMElement();
});

it("renders the New-resource button when the resource declares create", () => {
  renderForm(
    resource({
      create: {
        fields: [
          {
            name: "name",
            label: "Name",
            field_type: "text",
            required: true,
            options: [],
          },
        ],
        submit_label: "Create Biome",
        field_aliases: [],
      },
    }),
  );

  expect(screen.getByTestId("gough-manifest-biomes-create")).toHaveTextContent(
    "New Biome",
  );
});

it("opens the modal, submits, and posts the aliased payload to the generic typed create route", async () => {
  mockedApi.post.mockResolvedValue({ data: { id: "9" } });
  renderForm(
    resource({
      create: {
        fields: [
          {
            name: "name",
            label: "Name",
            field_type: "text",
            required: true,
            options: [],
          },
        ],
        submit_label: "Create Biome",
        field_aliases: [{ portal_name: "name", product_name: "biome_name" }],
      },
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-biomes-create"));
  fireEvent.change(await screen.findByLabelText(/^Name\*$/), {
    target: { value: "web" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create Biome" }));

  await waitFor(() =>
    expect(mockedApi.post).toHaveBeenCalledWith(
      "/products/7/resources/biomes",
      { biome_name: "web" },
    ),
  );
  // The modal closes on a successful submit.
  await waitFor(() =>
    expect(screen.queryByLabelText(/^Name\*$/)).not.toBeInTheDocument(),
  );
});

it("closes without submitting when the modal's own Cancel is clicked", async () => {
  renderForm(
    resource({
      create: {
        fields: [
          {
            name: "name",
            label: "Name",
            field_type: "text",
            required: true,
            options: [],
          },
        ],
        submit_label: "Create Biome",
        field_aliases: [],
      },
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-biomes-create"));
  await screen.findByLabelText(/^Name\*$/);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(screen.queryByLabelText(/^Name\*$/)).not.toBeInTheDocument();
  expect(mockedApi.post).not.toHaveBeenCalled();
});

it("binds a select field's options 1:1, with no synthesis step", async () => {
  renderForm(
    resource({
      create: {
        fields: [
          {
            name: "biome_kind",
            label: "Kind",
            field_type: "select",
            required: false,
            options: [
              { value: "custom", label: "Custom", disabled: false },
              { value: "k8s", label: "Kubernetes", disabled: false },
            ],
          },
        ],
        submit_label: "Create Biome",
        field_aliases: [],
      },
    }),
  );

  fireEvent.click(screen.getByTestId("gough-manifest-biomes-create"));
  expect(
    await screen.findByRole("option", { name: "Kubernetes" }),
  ).toBeInTheDocument();
});
