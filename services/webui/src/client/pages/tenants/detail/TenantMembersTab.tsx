/**
 * Members tab of the tenant detail page. Membership is server state, queried
 * per tenant and invalidated by the removal mutation.
 */

import Card from "../../../components/Card";
import {
  useTenantMembers,
  useRemoveTenantMember,
} from "../../../hooks/useTenants";

interface TenantMembersTabProps {
  tenantId: number;
}

export default function TenantMembersTab({ tenantId }: TenantMembersTabProps) {
  const membersQuery = useTenantMembers(tenantId);
  const removeMember = useRemoveTenantMember();

  const members = membersQuery.data ?? [];

  if (membersQuery.isLoading) {
    return (
      <Card title="Team Members">
        <div className="animate-pulse h-24 bg-slate-700 rounded" />
      </Card>
    );
  }

  return (
    <Card title="Team Members">
      {members.length === 0 ? (
        <p className="text-slate-400">No members found.</p>
      ) : (
        <div className="space-y-2">
          {members.map((member) => (
            <div
              key={member.user_id}
              className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0"
            >
              <div>
                <span className="text-slate-200">
                  {member.user_email || `User #${member.user_id}`}
                </span>
                <span className={`badge badge-${member.role} ml-2`}>
                  {member.role}
                </span>
              </div>
              <button
                onClick={() =>
                  removeMember.mutate({ tenantId, userId: member.user_id })
                }
                className="text-sm text-red-400 hover:text-red-300 focus:ring-2 focus:ring-sky-500 rounded"
                aria-label={`Remove ${member.user_email || `user ${member.user_id}`}`}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
