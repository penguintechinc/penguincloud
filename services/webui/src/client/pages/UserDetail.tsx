import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { usersApi } from "../hooks/useApi";
import Card from "../components/Card";
import { FormBuilder, FieldConfig } from "@penguintechinc/react-libs";
import type { User, UpdateUserData } from "../types";
import {
  formBoolean,
  formString,
  formUserRole,
  optionalFormString,
} from "../lib/formValues";

// User edit form field configuration
const getUserEditFields = (showPasswordField: boolean): FieldConfig[] => [
  {
    name: "full_name",
    label: "Full Name",
    type: "text",
    required: true,
    className: "md:col-span-1",
  },
  {
    name: "email",
    label: "Email",
    type: "email",
    required: true,
    className: "md:col-span-1",
  },
  {
    name: "role",
    label: "Role",
    type: "select",
    required: true,
    options: [
      { value: "viewer", label: "Viewer" },
      { value: "maintainer", label: "Maintainer" },
      { value: "admin", label: "Admin" },
    ],
    className: "md:col-span-1",
  },
  {
    name: "is_active",
    label: "Status",
    type: "select",
    required: true,
    options: [
      { value: "true", label: "Active" },
      { value: "false", label: "Inactive" },
    ],
    className: "md:col-span-1",
  },
  ...(showPasswordField
    ? [
        {
          name: "password",
          label: "New Password (leave blank to keep current)",
          type: "password" as const,
          minLength: 8,
          placeholder: "••••••••",
          className: "md:col-span-2",
        },
      ]
    : []),
];

export default function UserDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUser = async () => {
      if (!id) return;
      setIsLoading(true);
      try {
        const userData = await usersApi.get(parseInt(id, 10));
        setUser(userData);
        setError(null);
      } catch {
        setError("Failed to load user");
      } finally {
        setIsLoading(false);
      }
    };

    fetchUser();
  }, [id]);

  const handleSubmit = async (data: Record<string, unknown>) => {
    if (!id) return;

    try {
      // Built field-by-field rather than spreading the raw form record: the
      // select yields is_active as a string, and an empty password must be
      // omitted rather than sent as "".
      const updateData: UpdateUserData = {
        email: formString(data, "email"),
        full_name: formString(data, "full_name"),
        role: formUserRole(data, "role"),
        is_active: formBoolean(data, "is_active"),
        password: optionalFormString(data, "password"),
      };

      await usersApi.update(parseInt(id, 10), updateData);
      navigate("/users");
    } catch (err) {
      setError("Failed to update user");
      throw err; // Re-throw to keep FormBuilder in submitting state
    }
  };

  if (isLoading) {
    return (
      <div className="animate-pulse">
        <div className="h-8 bg-slate-700 rounded w-1/4 mb-6"></div>
        <div className="h-64 bg-slate-700 rounded"></div>
      </div>
    );
  }

  if (!user) {
    return (
      <Card>
        <p className="text-red-400">User not found</p>
      </Card>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">Edit User</h1>
        <p className="text-slate-400 mt-1">
          Update user information and permissions
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-400">
          {error}
        </div>
      )}

      {/* Edit Form */}
      <Card>
        <FormBuilder
          mode="inline"
          fields={getUserEditFields(true)}
          initialData={{
            full_name: user.full_name,
            email: user.email,
            role: user.role,
            is_active: String(user.is_active),
          }}
          submitLabel="Save Changes"
          cancelLabel="Cancel"
          onSubmit={handleSubmit}
          onCancel={() => navigate("/users")}
          error={error}
          className="grid grid-cols-1 md:grid-cols-2 gap-6"
        />

        {/* User Info */}
        <div className="border-t border-slate-700 pt-4 mt-6">
          <h3 className="text-sm font-medium text-slate-400 mb-3">
            User Information
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-slate-500">Created:</span>
              <span className="text-slate-300 ml-2">
                {new Date(user.created_at).toLocaleDateString()}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Last Updated:</span>
              <span className="text-slate-300 ml-2">
                {user.updated_at
                  ? new Date(user.updated_at).toLocaleDateString()
                  : "Never"}
              </span>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
