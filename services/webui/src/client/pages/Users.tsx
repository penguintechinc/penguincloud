/**
 * User administration page.
 * Server state is owned by TanStack Query; only modal visibility and the
 * pending-delete target are local component state.
 */

import { useState } from "react";
import Card from "../components/Card";
import Button from "../components/Button";
import { ConfirmDialog } from "../components/kit/ConfirmDialog";
import { FormBuilder } from "@penguintechinc/react-libs";
import { useUsers, useCreateUser, useDeleteUser } from "../hooks/useUsers";
import { formString, formUserRole } from "../lib/formValues";
import { userFields } from "./users/userFormFields";
import UserTable from "./users/UserTable";
import type { User } from "../types";

export default function Users() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<User | null>(null);

  const usersQuery = useUsers();
  const createUser = useCreateUser();
  const deleteUser = useDeleteUser();

  const users = usersQuery.data?.items ?? [];

  const error =
    (usersQuery.isError && "Failed to load users") ||
    (createUser.isError && "Failed to create user") ||
    (deleteUser.isError && "Failed to delete user") ||
    null;

  const handleCreateUser = async (data: Record<string, unknown>) => {
    await createUser.mutateAsync({
      email: formString(data, "email"),
      password: formString(data, "password"),
      full_name: formString(data, "full_name"),
      role: formUserRole(data, "role"),
    });
    setShowCreateModal(false);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    await deleteUser.mutateAsync(pendingDelete.id).catch(() => undefined);
    setPendingDelete(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">User Management</h1>
          <p className="text-slate-400 mt-1">
            Manage system users and permissions
          </p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>+ Add User</Button>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-400"
        >
          {error}
        </div>
      )}

      <Card>
        <UserTable
          users={users}
          isLoading={usersQuery.isLoading}
          onDelete={setPendingDelete}
        />
      </Card>

      <FormBuilder
        mode="modal"
        isOpen={showCreateModal}
        fields={userFields}
        title="Create New User"
        submitLabel="Create User"
        cancelLabel="Cancel"
        onSubmit={handleCreateUser}
        onCancel={() => setShowCreateModal(false)}
        error={createUser.isError ? "Failed to create user" : null}
      />

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title="Delete user"
        message={`Delete ${pendingDelete?.full_name || pendingDelete?.email}? This cannot be undone.`}
        confirmLabel="Delete"
        isDangerous
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
