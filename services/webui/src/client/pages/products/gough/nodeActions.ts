/**
 * The node verbs Gough actually registers, and what each one does.
 *
 * The 4G brief specified power actions (`/servers/{id}/power/{action}`).
 * Gough's api-manager registers no such route — that path exists only in its
 * stale committed openapi-spec.yaml. The real fleet verbs are below.
 *
 * Every one is destructive or provisioning, so every one carries a
 * confirmation string naming the physical consequence rather than asking
 * "are you sure?". All three require `products:gough:manage`; a read-only
 * token cannot reach them (asserted in test_gough_allowlist.py).
 */

export interface NodeAction {
  verb: "deploy" | "evacuate" | "reject";
  label: string;
  /** Shown in the ConfirmDialog. States the consequence, not the question. */
  confirmation: string;
}

export const NODE_ACTIONS: NodeAction[] = [
  {
    verb: "deploy",
    label: "Deploy",
    confirmation:
      "Deploying commissions this hardware and begins provisioning it.",
  },
  {
    verb: "evacuate",
    label: "Evacuate",
    confirmation:
      "Evacuating drains every workload off this node before removing it from service.",
  },
  {
    verb: "reject",
    label: "Reject",
    confirmation:
      "Rejecting removes this node from the fleet. It must be re-discovered to return.",
  },
];
