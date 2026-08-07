/**
 * Presentational table of user accounts.
 * Owns no data fetching — the Users page passes rows in and handles deletion.
 */

import { Link } from "react-router";
import type { User } from "../../types";

interface UserTableProps {
  users: User[];
  isLoading: boolean;
  onDelete: (user: User) => void;
}

export default function UserTable({
  users,
  isLoading,
  onDelete,
}: UserTableProps) {
  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4" data-testid="users-loading">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-slate-700 rounded" />
        ))}
      </div>
    );
  }

  return (
    <table className="table" data-testid="users-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Email</th>
          <th>Role</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {users.map((user) => (
          <tr key={user.id}>
            <td className="text-amber-400">{user.full_name}</td>
            <td className="text-slate-300">{user.email}</td>
            <td>
              <span className={`badge badge-${user.role}`}>{user.role}</span>
            </td>
            <td>
              <span
                className={user.is_active ? "text-green-400" : "text-red-400"}
              >
                {user.is_active ? "● Active" : "○ Inactive"}
              </span>
            </td>
            <td>
              <div className="flex items-center gap-2">
                <Link
                  to={`/users/${user.id}`}
                  className="text-amber-400 hover:text-amber-300 focus:ring-2 focus:ring-sky-500 rounded"
                >
                  Edit
                </Link>
                <button
                  onClick={() => onDelete(user)}
                  className="text-red-400 hover:text-red-300 focus:ring-2 focus:ring-sky-500 rounded"
                  aria-label={`Delete ${user.full_name || user.email}`}
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        ))}
        {users.length === 0 && (
          <tr>
            <td colSpan={5} className="text-center text-slate-400 py-8">
              No users found
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
