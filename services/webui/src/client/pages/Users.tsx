import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { usersApi } from '../hooks/useApi';
import Card from '../components/Card';
import Button from '../components/Button';
import { FormBuilder, FieldConfig } from '@penguintechinc/react-libs';
import type { User } from '../types';

// User form field configuration
const userFields: FieldConfig[] = [
  {
    name: 'full_name',
    label: 'Full Name',
    type: 'text',
    required: true,
    placeholder: 'John Doe',
    autoFocus: true,
  },
  {
    name: 'email',
    label: 'Email',
    type: 'email',
    required: true,
    placeholder: 'user@example.com',
  },
  {
    name: 'password',
    label: 'Password',
    type: 'password',
    required: true,
    minLength: 8,
    helperText: 'Minimum 8 characters required',
  },
  {
    name: 'role',
    label: 'Role',
    type: 'select',
    required: true,
    defaultValue: 'viewer',
    options: [
      { value: 'viewer', label: 'Viewer' },
      { value: 'maintainer', label: 'Maintainer' },
      { value: 'admin', label: 'Admin' },
    ],
  },
];

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const fetchUsers = async () => {
    setIsLoading(true);
    try {
      const response = await usersApi.list();
      setUsers(response.items);
      setError(null);
    } catch (err) {
      setError('Failed to load users');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreateUser = async (data: Record<string, any>) => {
    try {
      await usersApi.create(data as any);
      setShowCreateModal(false);
      fetchUsers();
      setError(null);
    } catch (err) {
      setError('Failed to create user');
      throw err; // Re-throw to keep FormBuilder in submitting state
    }
  };

  const handleDeleteUser = async (id: number) => {
    if (!confirm('Are you sure you want to delete this user?')) return;
    try {
      await usersApi.delete(id);
      fetchUsers();
    } catch (err) {
      setError('Failed to delete user');
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gold-400">User Management</h1>
          <p className="text-dark-400 mt-1">Manage system users and permissions</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>+ Add User</Button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          {error}
        </div>
      )}

      {/* Users Table */}
      <Card>
        {isLoading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-dark-700 rounded"></div>
            ))}
          </div>
        ) : (
          <table className="table">
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
                  <td className="text-gold-400">{user.full_name}</td>
                  <td className="text-dark-300">{user.email}</td>
                  <td>
                    <span className={`badge badge-${user.role}`}>{user.role}</span>
                  </td>
                  <td>
                    <span className={user.is_active ? 'text-green-400' : 'text-red-400'}>
                      {user.is_active ? '● Active' : '○ Inactive'}
                    </span>
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/users/${user.id}`}
                        className="text-gold-400 hover:text-gold-300"
                      >
                        Edit
                      </Link>
                      <button
                        onClick={() => handleDeleteUser(user.id)}
                        className="text-red-400 hover:text-red-300"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Create User Modal */}
      <FormBuilder
        mode="modal"
        isOpen={showCreateModal}
        fields={userFields}
        title="Create New User"
        submitLabel="Create User"
        cancelLabel="Cancel"
        onSubmit={handleCreateUser}
        onCancel={() => setShowCreateModal(false)}
        error={error}
      />
    </div>
  );
}
