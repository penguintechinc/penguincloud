/**
 * Field configuration for the user create form.
 * Split out of Users.tsx so the page stays under the 5000-character limit.
 */

import type { FieldConfig } from "@penguintechinc/react-libs";

export const userFields: FieldConfig[] = [
  {
    name: "full_name",
    label: "Full Name",
    type: "text",
    required: true,
    placeholder: "John Doe",
    autoFocus: true,
  },
  {
    name: "email",
    label: "Email",
    type: "email",
    required: true,
    placeholder: "user@example.com",
  },
  {
    name: "password",
    label: "Password",
    type: "password",
    required: true,
    minLength: 8,
    helperText: "Minimum 8 characters required",
  },
  {
    name: "role",
    label: "Role",
    type: "select",
    required: true,
    defaultValue: "viewer",
    options: [
      { value: "viewer", label: "Viewer" },
      { value: "maintainer", label: "Maintainer" },
      { value: "admin", label: "Admin" },
    ],
  },
];
