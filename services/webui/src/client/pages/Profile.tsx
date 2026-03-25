import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import Card from '../components/Card';
import Button from '../components/Button';
import { FormBuilder, FieldConfig } from '@penguintechinc/react-libs';
import api from '../lib/api';

// Profile edit form fields
const profileFields: FieldConfig[] = [
  {
    name: 'full_name',
    label: 'Full Name',
    type: 'text',
    required: true,
  },
  {
    name: 'email',
    label: 'Email',
    type: 'email',
    disabled: true,
    helperText: 'Contact admin to change email',
  },
  {
    name: 'current_password',
    label: 'Current Password',
    type: 'password',
    placeholder: 'Required to change password',
    helperText: 'Leave blank to keep current password',
  },
  {
    name: 'new_password',
    label: 'New Password',
    type: 'password',
    minLength: 8,
    helperText: 'Minimum 8 characters',
  },
  {
    name: 'confirm_password',
    label: 'Confirm New Password',
    type: 'password',
  },
];

export default function Profile() {
  const { user, checkAuth } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSave = async (data: Record<string, any>) => {
    setError(null);
    setSuccess(null);

    // Validate password match if changing password
    if (data.new_password && data.new_password !== data.confirm_password) {
      setError('New passwords do not match');
      throw new Error('Passwords do not match');
    }

    try {
      await api.put('/auth/me', {
        full_name: data.full_name,
        current_password: data.current_password || undefined,
        new_password: data.new_password || undefined,
      });

      setSuccess('Profile updated successfully');
      setIsEditing(false);
      checkAuth(); // Refresh user data
    } catch (err) {
      setError('Failed to update profile');
      throw err;
    }
  };

  if (!user) {
    return (
      <Card>
        <p className="text-dark-400">Loading...</p>
      </Card>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gold-400">Your Profile</h1>
        <p className="text-dark-400 mt-1">Manage your account settings</p>
      </div>

      {/* Messages */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-900/30 border border-green-700 rounded-lg text-green-400">
          {success}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Profile Info */}
        <Card className="lg:col-span-2" title="Profile Information">
          {isEditing ? (
            <FormBuilder
              mode="inline"
              fields={profileFields}
              initialData={{
                full_name: user.full_name,
                email: user.email,
                current_password: '',
                new_password: '',
                confirm_password: '',
              }}
              submitLabel="Save Changes"
              cancelLabel="Cancel"
              onSubmit={handleSave}
              onCancel={() => setIsEditing(false)}
              error={error}
            />
          ) : (
            <div className="space-y-4">
              <div>
                <span className="text-dark-400 text-sm">Full Name</span>
                <p className="text-gold-400">{user.full_name}</p>
              </div>
              <div>
                <span className="text-dark-400 text-sm">Email</span>
                <p className="text-gold-400">{user.email}</p>
              </div>
              <div>
                <span className="text-dark-400 text-sm">Password</span>
                <p className="text-dark-300">••••••••</p>
              </div>
              <Button variant="secondary" onClick={() => setIsEditing(true)}>
                Edit Profile
              </Button>
            </div>
          )}
        </Card>

        {/* Account Summary */}
        <Card title="Account Summary">
          <div className="space-y-4">
            <div>
              <span className="text-dark-400 text-sm">Role</span>
              <p>
                <span className={`badge badge-${user.role}`}>{user.role}</span>
              </p>
            </div>
            <div>
              <span className="text-dark-400 text-sm">Status</span>
              <p className={user.is_active ? 'text-green-400' : 'text-red-400'}>
                {user.is_active ? '● Active' : '○ Inactive'}
              </p>
            </div>
            <div>
              <span className="text-dark-400 text-sm">Member Since</span>
              <p className="text-dark-300">
                {new Date(user.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
