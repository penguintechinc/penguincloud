import { useState } from "react";
import {
  DataTable,
  DetailDrawer,
  FactList,
  RowOpenButtons,
} from "../../../components/kit";
import { TobogganingScreen } from "./TobogganingScreen";
import { BlockPagePreview } from "./BlockPagePreview";
import {
  BlockPageActions,
  CreateBlockPageModal,
  EditBlockPageModal,
  PublishConfirmDialog,
} from "./BlockPageDialogs";
import { ActionButton } from "../../../components/kit";
import { blockPageColumns } from "./blockPageColumns";
import { useTobogganingBlockPages } from "./useTobogganing";
import {
  useBlockPagePreview,
  useCreateBlockPage,
  usePublishBlockPage,
  useUpdateBlockPage,
} from "./useBlockPageMutations";
import type { TobogganingBlockPage } from "./types";

/**
 * SASE block pages — what a user sees when a request is blocked.
 *
 * The only Tobogganing screen with writes, and they are proxied rather than
 * typed adapter methods because none of them is asynchronous: the product
 * answers 200/201 with the resulting page, so there is no operation to poll.
 *
 * Preview renders inside a fully sandboxed iframe — see `BlockPagePreview`.
 */
export default function BlockPagesPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useTobogganingBlockPages();
  const [selected, setSelected] = useState<TobogganingBlockPage | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<TobogganingBlockPage | null>(null);
  const [publishing, setPublishing] = useState<TobogganingBlockPage | null>(
    null,
  );

  const create = useCreateBlockPage();
  const update = useUpdateBlockPage();
  const publish = usePublishBlockPage();
  const preview = useBlockPagePreview(productId);

  const rows = (data ?? []).map((page) => ({ ...page, id: String(page.id) }));

  const submitCreate = async (values: Record<string, unknown>) => {
    await create.mutateAsync({
      name: String(values.name ?? ""),
      markdown: String(values.markdown ?? ""),
    });
    setCreating(false);
  };

  const submitEdit = async (values: Record<string, unknown>) => {
    if (!editing) return;
    await update.mutateAsync({
      pageId: editing.id,
      markdown: String(values.markdown ?? ""),
    });
    setEditing(null);
  };

  return (
    <TobogganingScreen
      title="Block Pages"
      description="Pages shown to users whose requests this tenant's SASE policy blocks."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <div className="mb-4 flex justify-end">
        <ActionButton
          label="New block page"
          onClick={() => setCreating(true)}
          testId="tobogganing-blockpage-create"
        />
      </div>

      <DataTable<TobogganingBlockPage & { id: string }>
        columns={blockPageColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Tobogganing SASE block pages"
      />

      <RowOpenButtons
        rows={rows}
        label={(page) => page.name || page.id}
        onOpen={(page) => {
          preview.reset();
          setActiveTab("overview");
          setSelected(page);
        }}
        testIdPrefix="tobogganing-blockpage-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name || selected?.id || ""}
        subtitle={selected ? `${selected.status ?? "unknown"} page` : undefined}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => {
          preview.reset();
          setSelected(null);
        }}
        testId="tobogganing-blockpage-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                testId="tobogganing-facts"
                facts={[
                  ["Status", selected.status],
                  [
                    "Version",
                    typeof selected.version === "number"
                      ? String(selected.version)
                      : null,
                  ],
                  ["Updated by", selected.updated_by],
                  ["Updated", selected.updated_at],
                ]}
              />
            ) : null,
          },
          {
            id: "source",
            label: "Markdown",
            content: (
              // Escaped text, not rendered markup. This is the authored
              // source; rendering it here would be the same injection the
              // preview tab exists to sandbox.
              <pre
                className="text-xs text-slate-200 whitespace-pre-wrap break-all"
                data-testid="tobogganing-blockpage-source"
              >
                {selected?.markdown ?? ""}
              </pre>
            ),
          },
          {
            id: "preview",
            label: "Preview",
            content: (
              <BlockPagePreview
                html={preview.html}
                isLoading={preview.isLoading}
                error={preview.error}
              />
            ),
          },
        ]}
        actions={
          <BlockPageActions
            onPreview={() => {
              if (!selected) return;
              setActiveTab("preview");
              void preview.run(selected.id);
            }}
            onEdit={() => setEditing(selected)}
            onPublish={() => setPublishing(selected)}
          />
        }
      />

      <CreateBlockPageModal
        isOpen={creating}
        onClose={() => setCreating(false)}
        onSubmit={submitCreate}
      />

      <EditBlockPageModal
        page={editing}
        onClose={() => setEditing(null)}
        onSubmit={submitEdit}
      />

      <PublishConfirmDialog
        page={publishing}
        isLoading={publish.isPending}
        onConfirm={() => {
          if (!publishing) return;
          publish.mutate(
            { pageId: publishing.id },
            { onSuccess: () => setPublishing(null) },
          );
        }}
        onCancel={() => setPublishing(null)}
      />
    </TobogganingScreen>
  );
}
