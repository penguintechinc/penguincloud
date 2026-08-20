import { useState } from "react";
import { FormModalBuilder } from "@penguintechinc/react-libs";
import {
  ActionButton,
  ConfirmDialog,
  DataTable,
} from "../../../components/kit";
import { TobogganingScreen } from "./TobogganingScreen";
import { swgPolicyColumns, swgPolicyFields } from "./swgPolicyColumns";
import { tobogganingApi } from "../../../api/resources/tobogganing";
import {
  TOBOGGANING_KINDS,
  useTobogganingMutation,
  useTobogganingSwgPolicies,
} from "./useTobogganing";
import type { TobogganingSwgPolicy } from "./types";

/** The payload the product's PUT reads. `tenant` is deliberately absent. */
interface SwgPolicyInput {
  scope: string;
  scope_id?: string | null;
  category: string;
  action: string;
}

/** Normalise form values into the product's shape, dropping empty ids. */
function toPolicy(values: Record<string, unknown>): SwgPolicyInput {
  const scope = String(values.scope ?? "tenant");
  const rawId = String(values.scope_id ?? "").trim();
  return {
    scope,
    // A tenant policy has no subject; sending "" would be stored as a scope_id
    // that matches nothing rather than as "everyone".
    scope_id: scope === "tenant" || rawId === "" ? null : rawId,
    category: String(values.category ?? "").trim(),
    action: String(values.action ?? ""),
  };
}

/**
 * SASE secure-web-gateway category policies.
 *
 * `PUT /sase/swg/policy` is an UPSERT keyed on (scope, scope_id, category), so
 * saving a category that already has a policy replaces its action rather than
 * adding a row. That is invisible in the form, so the screen detects the
 * collision itself and confirms — otherwise "Save" silently changes an
 * existing rule the operator may not have been looking at.
 */
export default function SwgPolicyPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useTobogganingSwgPolicies();
  const [formOpen, setFormOpen] = useState(false);
  const [replacing, setReplacing] = useState<{
    input: SwgPolicyInput;
    existing: TobogganingSwgPolicy;
  } | null>(null);

  const save = useTobogganingMutation<SwgPolicyInput, unknown>(
    TOBOGGANING_KINDS.swgPolicies,
    (id, vars) => tobogganingApi.setSwgPolicy(id, vars),
  );

  const rows = (data ?? []).map((policy, index) => ({
    ...policy,
    id: String(policy.id ?? `${policy.scope}-${policy.category}-${index}`),
  }));

  /** The policy this input would overwrite, if the product already holds one. */
  const collision = (input: SwgPolicyInput): TobogganingSwgPolicy | undefined =>
    (data ?? []).find(
      (policy) =>
        policy.scope === input.scope &&
        (policy.scope_id ?? null) === input.scope_id &&
        policy.category === input.category,
    );

  const submit = async (values: Record<string, unknown>): Promise<void> => {
    const input = toPolicy(values);
    const existing = collision(input);
    if (existing && existing.action !== input.action) {
      // Not a save attempt yet — closing here just swaps the form for the
      // confirmation. Nothing has been sent, so there is no outcome to hide.
      setFormOpen(false);
      setReplacing({ input, existing });
      return;
    }
    // Deliberately NOT closing first: `FormModalBuilder` only calls its own
    // `onClose` after `onSubmit` resolves, and leaves the modal open (with
    // the operator's entered values intact) if it throws. Closing here
    // unconditionally, as this used to, discarded that behaviour — a
    // rejected save closed the form before the rejection was known, so
    // nothing was left on screen to show it had failed. The global
    // `MutationCache.onError` (lib/queryClient.ts) still surfaces the
    // failure via MutationErrorBanner regardless of which path this takes.
    await save.mutateAsync(input);
  };

  return (
    <TobogganingScreen
      title="SWG Policy"
      description="Category policies applied to this tenant's web traffic."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <div className="mb-4 flex justify-end">
        <ActionButton
          label="Set policy"
          onClick={() => setFormOpen(true)}
          testId="tobogganing-swg-set"
        />
      </div>

      <DataTable<TobogganingSwgPolicy & { id: string }>
        columns={swgPolicyColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Tobogganing SWG category policies"
      />

      <FormModalBuilder
        title="Set category policy"
        fields={swgPolicyFields}
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={submit}
        submitButtonText="Save"
      />

      <ConfirmDialog
        isOpen={replacing !== null}
        title="Replace an existing policy"
        message={
          replacing
            ? `"${replacing.input.category}" is already set to ` +
              `"${replacing.existing.action}" at this scope. Saving replaces ` +
              `it with "${replacing.input.action}" — it does not add a second ` +
              `rule.`
            : ""
        }
        confirmLabel="Replace"
        isDangerous
        isLoading={save.isPending}
        onConfirm={() => {
          if (!replacing) return;
          save.mutate(replacing.input, {
            onSuccess: () => setReplacing(null),
          });
        }}
        onCancel={() => setReplacing(null)}
        testId="tobogganing-swg-replace-confirm"
      />
    </TobogganingScreen>
  );
}
