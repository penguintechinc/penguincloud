/**
 * The manifest's `create: FormSpec` bound to react-libs' REAL `FormBuilder`
 * (`mode="modal"`) — see `manifestFormFields.ts`'s module doc for why this
 * is now a straight `FieldConfig` projection rather than an approximation.
 *
 * Renders nothing when the resource declares no `create` — the same
 * "absence is a fact, not a default" discipline the rest of this kit
 * applies to a missing `list`/`item_path`.
 */
import { useState } from "react";
import { FormBuilder } from "@penguintechinc/react-libs";
import { ActionButton } from "./ActionButton";
import { toFieldConfig, applyFieldAliases } from "./manifestFormFields";
import { useCreateManifestResource } from "./manifestMutations";
import type { ResourceDescriptor } from "./manifestTypes";

export interface ManifestCreateFormProps {
  productType: string;
  tenantId: number | undefined;
  productId: number | undefined;
  resource: ResourceDescriptor;
}

export function ManifestCreateForm({
  productType,
  tenantId,
  productId,
  resource,
}: ManifestCreateFormProps) {
  const [isOpen, setIsOpen] = useState(false);
  const create = useCreateManifestResource(
    productType,
    tenantId,
    productId,
    resource.kind,
  );

  if (!resource.create) return null;
  const formSpec = resource.create;
  const testIdPrefix = `${productType}-manifest-${resource.kind}`;

  return (
    <>
      <div className="mb-4 flex justify-end">
        <ActionButton
          label={`New ${resource.label}`}
          onClick={() => setIsOpen(true)}
          testId={`${testIdPrefix}-create`}
        />
      </div>

      <FormBuilder
        mode="modal"
        isOpen={isOpen}
        title={`New ${resource.label}`}
        fields={formSpec.fields.map(toFieldConfig)}
        submitLabel={formSpec.submit_label}
        loading={create.isPending}
        onCancel={() => setIsOpen(false)}
        onSubmit={async (values: Record<string, unknown>): Promise<void> => {
          await create.mutateAsync(
            applyFieldAliases(values, formSpec.field_aliases),
          );
          setIsOpen(false);
        }}
      />
    </>
  );
}
