import { FormModalBuilder } from "@penguintechinc/react-libs";
import { ActionButton, ConfirmDialog } from "../../../components/kit";
import { blockPageEditFields, blockPageFields } from "./blockPageColumns";
import type { TobogganingBlockPage } from "./types";

interface CreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

/** The create form. A new page is always a DRAFT — status is not offered. */
export function CreateBlockPageModal({
  isOpen,
  onClose,
  onSubmit,
}: CreateModalProps) {
  return (
    <FormModalBuilder
      title="New block page"
      fields={blockPageFields}
      isOpen={isOpen}
      onClose={onClose}
      onSubmit={onSubmit}
      submitButtonText="Create draft"
      width="xl"
    />
  );
}

interface EditModalProps {
  page: TobogganingBlockPage | null;
  onClose: () => void;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

/**
 * The edit form.
 *
 * Only markdown. The product's update route reads `markdown` and nothing else,
 * so a name field here would accept an edit and discard it — the worst of the
 * three possible behaviours, because the operator is told it saved.
 */
export function EditBlockPageModal({
  page,
  onClose,
  onSubmit,
}: EditModalProps) {
  if (!page) return null;
  return (
    <FormModalBuilder
      // Keyed by id so switching pages remounts the form with the new
      // defaultValue; without it the modal would keep the first page's source.
      key={page.id}
      title={`Edit ${page.name ?? "block page"}`}
      fields={blockPageEditFields.map((field) => ({
        ...field,
        defaultValue: page.markdown ?? "",
      }))}
      isOpen
      onClose={onClose}
      onSubmit={onSubmit}
      submitButtonText="Save"
      width="xl"
    />
  );
}

interface DrawerActionsProps {
  onPreview: () => void;
  onEdit: () => void;
  onPublish: () => void;
}

/** Verb buttons in the drawer footer. Publish is the one that changes what users see. */
export function BlockPageActions({
  onPreview,
  onEdit,
  onPublish,
}: DrawerActionsProps) {
  return (
    <>
      <ActionButton
        label="Preview"
        variant="ghost"
        onClick={onPreview}
        testId="tobogganing-blockpage-preview"
      />
      <ActionButton
        label="Edit"
        onClick={onEdit}
        testId="tobogganing-blockpage-edit"
      />
      <ActionButton
        label="Publish"
        // Danger styling: publishing is what makes this page the one every
        // blocked user in the tenant sees. It is not destructive, but it is
        // immediately externally visible, which is the distinction the variant
        // exists to draw.
        variant="danger"
        onClick={onPublish}
        testId="tobogganing-blockpage-publish"
      />
    </>
  );
}

interface PublishConfirmProps {
  page: TobogganingBlockPage | null;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation for publishing.
 *
 * The message names the consequence an operator will not predict: publishing
 * takes effect for every blocked user in the tenant at once, and there is no
 * unpublish route in the product — the only way back is to publish different
 * content.
 */
export function PublishConfirmDialog({
  page,
  isLoading,
  onConfirm,
  onCancel,
}: PublishConfirmProps) {
  return (
    <ConfirmDialog
      isOpen={page !== null}
      title="Publish block page"
      message={
        page
          ? `Publishing "${page.name ?? page.id}" makes it the page every ` +
            `blocked user in this tenant sees, immediately. Tobogganing has ` +
            `no unpublish route — reverting means publishing different content.`
          : ""
      }
      confirmLabel="Publish"
      isDangerous
      isLoading={isLoading}
      onConfirm={onConfirm}
      onCancel={onCancel}
      testId="tobogganing-blockpage-publish-confirm"
    />
  );
}
