# React Component Library (@penguintechinc/react-libs)

Reusable React components for building consistent, type-safe user interfaces with Tailwind CSS styling.

## Installation

```bash
npm install @penguintechinc/react-libs
# or
yarn add @penguintechinc/react-libs
```

## Components

### FormModalBuilder

A powerful, flexible form modal builder that dynamically generates forms from configuration objects with automatic tabbing and comprehensive theming.

#### Features

- ✨ **Dynamic Form Generation** - Build forms from simple configuration objects
- 📝 **16+ Input Types** - text, email, password, number, select, checkbox, radio, textarea, date, time, file, etc.
- 🔐 **Password Generation** - Built-in password generator with customizable length
- 📄 **File Upload with Drag & Drop** - Single and multiple file uploads with size limits
- 📋 **Multiline Arrays** - Split text by newlines to create string arrays
- 📑 **Automatic Tabs** - Creates tabs when field count exceeds threshold (default: 8 fields)
- 🎛️ **Manual Tab Control** - Organize fields by category using `tab` property or explicit tab configuration
- 🔄 **Next/Previous Navigation** - Multi-step form workflow with tab navigation
- ⚠️ **Tab Error Indicators** - Visual indicators show which tabs have validation errors
- ✅ **Zod Schema Validation** - Type-safe validation with Zod schemas
- 🔍 **Conditional Fields** - Show/hide fields based on other field values
- 🎨 **Comprehensive Theming** - Full color customization for all elements (27 properties)
- 🌙 **Dark Mode Default** - Beautiful navy & gold dark theme out of the box
- 📱 **Responsive Design** - Mobile-first design with Tailwind CSS
- ⚡ **TypeScript Support** - Full type safety with TypeScript
- 🔄 **Async Submit** - Promise-based form submission
- 📏 **No Scrollbars Needed** - Tabs keep forms clean and organized
- 🎯 **Required Indicators** - Visual markers for required fields
- ⚠️ **Error Messages** - Field-level validation errors
- 💡 **Help Text** - Additional context shown below fields
- 🔒 **Field States** - Disabled and hidden field support

#### Quick Start

```tsx
import { useState } from 'react';
import { FormModalBuilder, FormField } from '@penguintechinc/react-libs';

function App() {
  const [isOpen, setIsOpen] = useState(false);

  const fields: FormField[] = [
    {
      name: 'username',
      type: 'text',
      label: 'Username',
      required: true,
      placeholder: 'Enter username',
    },
    {
      name: 'email',
      type: 'email',
      label: 'Email',
      required: true,
    },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Form data:', data);
    // Make API call
  };

  return (
    <>
      <button onClick={() => setIsOpen(true)}>Open Form</button>
      <FormModalBuilder
        title="User Registration"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
      />
    </>
  );
}
```

#### Automatic Tabbing

Forms automatically create tabs when field count exceeds 8 (configurable threshold). This eliminates scrollbars and provides a clean, multi-step form experience.

**Automatic Tabs Example:**
```tsx
// With 12 fields, tabs are auto-generated: "General" and "Step 2"
const fields: FormField[] = [
  // ... 12 fields defined here
];

<FormModalBuilder
  title="User Registration"
  fields={fields}
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  // Tabs auto-created! Default: 8 field threshold, 6 fields per tab
/>
```

**Manual Tab Assignment:**
```tsx
const fields: FormField[] = [
  { name: 'firstName', type: 'text', label: 'First Name', tab: 'Personal Info' },
  { name: 'lastName', type: 'text', label: 'Last Name', tab: 'Personal Info' },
  { name: 'username', type: 'text', label: 'Username', tab: 'Account' },
  { name: 'password', type: 'password', label: 'Password', tab: 'Account' },
];
```

**Explicit Tab Configuration:**
```tsx
import { FormTab } from '@penguintechinc/react-libs';

const tabs: FormTab[] = [
  {
    id: 'basic',
    label: 'Basic Info',
    fields: [
      { name: 'name', type: 'text', label: 'Product Name', required: true },
      { name: 'price', type: 'number', label: 'Price', required: true },
    ],
  },
  {
    id: 'inventory',
    label: 'Inventory',
    fields: [
      { name: 'stock', type: 'number', label: 'Stock', required: true },
    ],
  },
];

const allFields = tabs.flatMap((tab) => tab.fields);

<FormModalBuilder
  title="Add Product"
  fields={allFields}
  tabs={tabs}  // Explicit tab control
  // ... other props
/>
```

#### Comprehensive Theming

**Default Dark Mode (Navy & Gold):**
```tsx
// No colors prop needed - beautiful dark mode out of the box!
<FormModalBuilder
  title="Create Account"
  fields={fields}
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  // Defaults to navy background with gold accents
/>
```

**Custom Light Mode:**
```tsx
import { ColorConfig } from '@penguintechinc/react-libs';

const lightTheme: ColorConfig = {
  modalBackground: 'bg-white',
  headerBackground: 'bg-white',
  footerBackground: 'bg-gray-50',
  overlayBackground: 'bg-gray-500 bg-opacity-75',
  titleText: 'text-gray-900',
  labelText: 'text-gray-700',
  descriptionText: 'text-gray-500',
  errorText: 'text-red-600',
  buttonText: 'text-white',
  fieldBackground: 'bg-white',
  fieldBorder: 'border-gray-300',
  fieldText: 'text-gray-900',
  fieldPlaceholder: 'placeholder-gray-400',
  focusRing: 'focus:ring-blue-500',
  focusBorder: 'focus:border-blue-500',
  primaryButton: 'bg-blue-600',
  primaryButtonHover: 'hover:bg-blue-700',
  secondaryButton: 'bg-white',
  secondaryButtonHover: 'hover:bg-gray-50',
  secondaryButtonBorder: 'border-gray-300',
  activeTab: 'text-blue-600',
  activeTabBorder: 'border-blue-500',
  inactiveTab: 'text-gray-500',
  inactiveTabHover: 'hover:text-gray-700 hover:border-gray-300',
  tabBorder: 'border-gray-200',
  errorTabText: 'text-red-600',
  errorTabBorder: 'border-red-300',
};

<FormModalBuilder colors={lightTheme} /* ... other props */ />
```

**Available Theme Properties:**
- `modalBackground`, `headerBackground`, `footerBackground`, `overlayBackground`
- `titleText`, `labelText`, `descriptionText`, `errorText`, `buttonText`
- `fieldBackground`, `fieldBorder`, `fieldText`, `fieldPlaceholder`
- `focusRing`, `focusBorder`
- `primaryButton`, `primaryButtonHover`
- `secondaryButton`, `secondaryButtonHover`, `secondaryButtonBorder`
- `activeTab`, `activeTabBorder`, `inactiveTab`, `inactiveTabHover`
- `tabBorder`, `errorTabText`, `errorTabBorder`

#### Password Generation

The `password_generate` field type includes a built-in password generator:

```tsx
import { FormField } from '@penguintechinc/react-libs';

const fields: FormField[] = [
  {
    name: 'password',
    type: 'password_generate',
    label: 'Password',
    required: true,
    placeholder: 'Enter or generate password',
    helpText: 'Click "Generate" for a secure random password',
    onPasswordGenerated: (password) => {
      console.log('Generated password:', password);
      // Optionally copy to clipboard or store
    },
  },
];
```

**Features:**
- Click button to generate random password (14 chars default)
- Mixed case letters and numbers
- Automatically fills the field
- Optional callback when password is generated
- Visual feedback with generate icon

**Utility Function:**
```tsx
import { generatePassword } from '@penguintechinc/react-libs';

// Generate custom length password
const customPassword = generatePassword(20);  // 20 characters
```

#### File Upload with Drag & Drop

Both single and multiple file uploads support drag & drop functionality:

**Single File Upload:**
```tsx
{
  name: 'avatar',
  type: 'file',
  label: 'Profile Picture',
  accept: 'image/*',
  maxFileSize: 5 * 1024 * 1024,  // 5MB limit
  helpText: 'Upload a profile picture (max 5MB)',
}
```

**Multiple File Upload:**
```tsx
{
  name: 'attachments',
  type: 'file_multiple',
  label: 'Attachments',
  accept: '.pdf,.doc,.docx',
  maxFileSize: 10 * 1024 * 1024,  // 10MB per file
  maxFiles: 5,                     // Maximum 5 files
  helpText: 'Upload up to 5 documents (max 10MB each)',
}
```

**Features:**
- Drag and drop files onto the upload area
- Click to browse file system
- Visual feedback during drag
- File size validation with error messages
- File count limits for multiple uploads
- File type filtering via `accept` attribute
- Progress indication during upload

#### Multiline Arrays

The `multiline` field type splits input by newlines into a string array:

```tsx
{
  name: 'domains',
  type: 'multiline',
  label: 'Allowed Domains',
  rows: 5,
  placeholder: 'example.com\nanother-domain.com\nthird-domain.com',
  helpText: 'Enter one domain per line',
}
```

**Use Cases:**
- Domain whitelist/blacklist
- Email lists
- File paths
- Tags or keywords
- Configuration items

**Returns:** `string[]` array with each line as an element (empty lines removed)

#### Zod Schema Validation

Use Zod schemas for type-safe, powerful validation:

```tsx
import { z } from '@penguintechinc/react-libs';

const fields: FormField[] = [
  {
    name: 'username',
    type: 'text',
    label: 'Username',
    schema: z.string()
      .min(3, 'Username must be at least 3 characters')
      .max(20, 'Username must be at most 20 characters')
      .regex(/^[a-z0-9_]+$/, 'Only lowercase letters, numbers, and underscores'),
  },
  {
    name: 'email',
    type: 'email',
    label: 'Email',
    schema: z.string()
      .email('Must be a valid email')
      .endsWith('@company.com', 'Must be a company email'),
  },
  {
    name: 'age',
    type: 'number',
    label: 'Age',
    schema: z.number()
      .min(18, 'Must be 18 or older')
      .max(120, 'Invalid age'),
  },
];
```

**Benefits:**
- Type-safe validation with TypeScript
- Chainable validation rules
- Rich error messages
- Automatic type coercion
- Custom refinements and transforms

**Note:** The `z` object is re-exported from `@penguintechinc/react-libs` for convenience.

#### Conditional Field Visibility

Show or hide fields based on other field values:

**Using `triggerField`:**
```tsx
const fields: FormField[] = [
  {
    name: 'enableNotifications',
    type: 'checkbox',
    label: 'Enable Notifications',
    defaultValue: false,
  },
  {
    name: 'notificationEmail',
    type: 'email',
    label: 'Notification Email',
    triggerField: 'enableNotifications',  // Only shows when enableNotifications is truthy
  },
];
```

**Using `showWhen` for complex logic:**
```tsx
{
  name: 'customDomain',
  type: 'text',
  label: 'Custom Domain',
  showWhen: (values) => {
    return values.plan === 'enterprise' && values.advancedFeatures === true;
  },
  helpText: 'Only available for Enterprise plan with advanced features',
}
```

**Features:**
- Hide fields until trigger condition is met
- Complex conditional logic with `showWhen`
- Validation only runs on visible fields
- Smooth show/hide transitions
- Values preserved when hidden

### SidebarMenu

A collapsible sidebar navigation component inspired by Elder's sidebar, with role-based permissions and full theme customization.

#### Features

- 📂 **Collapsible Categories** - Organize menu items into expandable sections
- 🔒 **Role-Based Permissions** - Show/hide menu items based on user roles
- 🎨 **Comprehensive Theming** - Full color customization for all elements (14 properties)
- 🌙 **Elder-Inspired Default** - Slate dark theme with blue accent
- 🎯 **Active Item Highlighting** - Flexible path matching with exact and prefix modes
- 🔄 **Navigation Callbacks** - Custom click handlers for routing integration
- ✨ **Customizable Icons** - Use any React icon library
- 📏 **Configurable Width** - Adjustable sidebar width
- 🎨 **Sticky Footer** - Fixed footer section for profile/logout items
- 🖱️ **Smooth Transitions** - Polished hover states and animations
- 📱 **Fixed Sidebar** - Scrollable navigation with fixed header and footer

#### Quick Start

```tsx
import { useState } from 'react';
import { SidebarMenu, MenuCategory } from '@penguintechinc/react-libs';
import { Home, Users, Settings } from 'lucide-react';

function App() {
  const [currentPath, setCurrentPath] = useState('/');

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Dashboard', href: '/', icon: Home },
      ],
    },
    {
      header: 'Management',
      collapsible: true,
      items: [
        { name: 'Users', href: '/users', icon: Users },
        { name: 'Teams', href: '/teams', icon: Users },
      ],
    },
  ];

  return (
    <div className="h-screen">
      <SidebarMenu
        logo={<img src="/logo.png" alt="Logo" className="h-12" />}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={[
          { name: 'Settings', href: '/settings', icon: Settings },
        ]}
      />

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">
          <h1>Current Page: {currentPath}</h1>
        </main>
      </div>
    </div>
  );
}
```

#### Role-Based Access Control

```tsx
const categories: MenuCategory[] = [
  {
    header: 'Administration',
    collapsible: true,
    items: [
      {
        name: 'Settings',
        href: '/admin/settings',
        icon: Settings,
        roles: ['admin']  // Only visible to admin users
      },
      {
        name: 'Audit Logs',
        href: '/admin/audit',
        icon: FileText,
        roles: ['admin', 'maintainer']  // Multiple roles
      },
    ],
  },
];

<SidebarMenu
  categories={categories}
  currentPath={currentPath}
  userRole="admin"  // Current user's role
  onNavigate={setCurrentPath}
/>
```

#### Theming

**Default Elder Theme:**
```tsx
// No colors prop needed - Elder theme out of the box!
<SidebarMenu
  logo={<span className="text-xl font-bold">App</span>}
  categories={categories}
  currentPath={currentPath}
  onNavigate={setCurrentPath}
  // Defaults to slate-800 background with primary-600 accent
/>
```

**Custom Navy & Gold Theme:**
```tsx
import { SidebarColorConfig } from '@penguintechinc/react-libs';

const navyGoldTheme: SidebarColorConfig = {
  sidebarBackground: 'bg-slate-900',
  sidebarBorder: 'border-slate-700',
  logoSectionBorder: 'border-slate-700',
  categoryHeaderText: 'text-amber-400',
  menuItemText: 'text-amber-300',
  menuItemHover: 'hover:bg-slate-800 hover:text-amber-200',
  menuItemActive: 'bg-amber-500',
  menuItemActiveText: 'text-slate-900',
  collapseIndicator: 'text-amber-400',
  footerBorder: 'border-slate-700',
  footerButtonText: 'text-amber-300',
  footerButtonHover: 'hover:bg-slate-800 hover:text-amber-200',
  scrollbarTrack: 'bg-slate-900',
  scrollbarThumb: 'bg-slate-700',
  scrollbarThumbHover: 'hover:bg-slate-600',
};

<SidebarMenu colors={navyGoldTheme} /* ... other props */ />
```

**Available Theme Properties:**
- `sidebarBackground`, `sidebarBorder`, `logoSectionBorder`
- `categoryHeaderText`, `menuItemText`, `menuItemHover`
- `menuItemActive`, `menuItemActiveText`, `collapseIndicator`
- `footerBorder`, `footerButtonText`, `footerButtonHover`
- `scrollbarTrack`, `scrollbarThumb`, `scrollbarThumbHover`

#### Custom Icons

```tsx
import { ChevronDown, ChevronRight } from 'lucide-react';

<SidebarMenu
  collapseIcon={ChevronDown}  // Custom collapse icon
  expandIcon={ChevronRight}   // Custom expand icon
  categories={categories}
  // ... other props
/>
```

## API Reference

### FormModalBuilderProps

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `string` | Required | Modal title text |
| `fields` | `FormField[]` | Required | Array of form field definitions |
| `tabs` | `FormTab[]` | Optional | Explicit tab configuration |
| `isOpen` | `boolean` | Required | Controls modal visibility |
| `onClose` | `() => void` | Required | Close handler function |
| `onSubmit` | `(data: Record<string, any>) => Promise<void> \| void` | Required | Form submission handler |
| `submitButtonText` | `string` | `"Submit"` | Text for submit button |
| `cancelButtonText` | `string` | `"Cancel"` | Text for cancel button |
| `width` | `'sm' \| 'md' \| 'lg' \| 'xl' \| '2xl'` | `'md'` | Modal width |
| `backgroundColor` | `string` | `'bg-white'` | Tailwind background color class |
| `maxHeight` | `string` | `'max-h-[80vh]'` | Tailwind max-height class |
| `zIndex` | `number` | `9999` | Z-index for modal overlay |
| `autoTabThreshold` | `number` | `8` | Auto-create tabs if fields > threshold |
| `fieldsPerTab` | `number` | `6` | Fields per auto-generated tab |
| `colors` | `ColorConfig` | Navy/gold theme | Custom color configuration |

### SidebarMenuProps

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `logo` | `ReactNode` | Optional | Logo element (image, text, etc.) |
| `categories` | `MenuCategory[]` | Required | Menu categories and items |
| `currentPath` | `string` | Required | Current active path |
| `onNavigate` | `(href: string) => void` | Optional | Navigation callback |
| `footerItems` | `MenuItem[]` | `[]` | Footer menu items |
| `userRole` | `string` | Optional | Current user role for permissions |
| `width` | `string` | `'w-64'` | Sidebar width class |
| `colors` | `SidebarColorConfig` | Elder theme | Custom color configuration |
| `collapseIcon` | `React.ComponentType` | ChevronDown | Collapse icon component |
| `expandIcon` | `React.ComponentType` | ChevronRight | Expand icon component |

### FormField Interface

```typescript
interface FormField {
  // Basic properties
  name: string;                     // Unique field identifier
  type: InputType;                  // Input type (see Supported Input Types)
  label: string;                    // Display label
  description?: string;             // Optional description text
  helpText?: string;                // Additional help text shown below field

  // Value properties
  defaultValue?: any;               // Default field value
  placeholder?: string;             // Placeholder text

  // Validation properties
  required?: boolean;               // Mark as required
  schema?: ZodType;                 // Custom Zod schema for validation
  validation?: (value: any) => string | null;  // Legacy custom validator (deprecated)

  // Field state
  disabled?: boolean;               // Disable field editing
  hidden?: boolean;                 // Hide field from display

  // Selection field properties (select, radio)
  options?: Option[];               // Options for select/radio

  // Number field properties
  min?: number;                     // Min value (number fields)
  max?: number;                     // Max value (number fields)

  // Text field properties
  pattern?: string;                 // Regex pattern for validation

  // File upload properties
  accept?: string;                  // File types (e.g., "image/*", ".pdf,.doc")
  maxFileSize?: number;             // Maximum file size in bytes
  maxFiles?: number;                // Maximum number of files (file_multiple)

  // Textarea properties
  rows?: number;                    // Rows for textarea/multiline

  // Tab organization
  tab?: string;                     // Tab name for manual tab assignment

  // Conditional visibility
  triggerField?: string;            // Field name that must be truthy for this field to show
  showWhen?: (values: Record<string, any>) => boolean;  // Custom visibility logic

  // Password generation
  onPasswordGenerated?: (password: string) => void;  // Callback for password_generate type
}
```

### FormTab Interface

```typescript
interface FormTab {
  id: string;                       // Unique tab identifier
  label: string;                    // Tab display label
  fields: FormField[];              // Fields in this tab
}
```

### MenuItem Interface

```typescript
interface MenuItem {
  name: string;                      // Display name
  href: string;                      // Navigation path
  icon?: React.ComponentType<{ className?: string }>;  // Optional icon
  roles?: string[];                  // Required roles (if any)
}
```

### MenuCategory Interface

```typescript
interface MenuCategory {
  header?: string;                   // Category header text (optional)
  collapsible?: boolean;             // Allow collapse/expand
  items: MenuItem[];                 // Menu items in category
}
```

### Supported Input Types

| Type | Description | Props | Returns |
|------|-------------|-------|---------|
| `text` | Standard text input | `placeholder`, `pattern` | `string` |
| `email` | Email input with validation | `placeholder` | `string` |
| `password` | Password input | `placeholder` | `string` |
| `password_generate` | Password with generate button | `placeholder`, `onPasswordGenerated` | `string` |
| `number` | Number input | `min`, `max`, `placeholder` | `number` |
| `tel` | Telephone input | `pattern`, `placeholder` | `string` |
| `url` | URL input with validation | `placeholder` | `string` |
| `textarea` | Multi-line text input (trimmed) | `rows`, `placeholder` | `string` |
| `multiline` | Multi-line input split by newlines | `rows`, `placeholder` | `string[]` |
| `select` | Dropdown selection | `options` (required) | `string \| number` |
| `checkbox` | Single checkbox | `defaultValue` | `boolean` |
| `radio` | Radio button group | `options` (required) | `string \| number` |
| `date` | Date picker | - | `string` (YYYY-MM-DD) |
| `time` | Time picker | - | `string` (HH:mm) |
| `datetime-local` | Date and time picker | - | `string` (ISO) |
| `file` | Single file upload with drag & drop | `accept`, `maxFileSize` | `File` |
| `file_multiple` | Multiple file upload with drag & drop | `accept`, `maxFileSize`, `maxFiles` | `File[]` |

## Examples

### Advanced User Registration with All Features

```tsx
import { useState } from 'react';
import { FormModalBuilder, FormField, z } from '@penguintechinc/react-libs';

function AdvancedRegistration() {
  const [isOpen, setIsOpen] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState('');

  const fields: FormField[] = [
    // Basic Info Tab
    {
      name: 'firstName',
      type: 'text',
      label: 'First Name',
      required: true,
      tab: 'Basic Info',
    },
    {
      name: 'lastName',
      type: 'text',
      label: 'Last Name',
      required: true,
      tab: 'Basic Info',
    },
    {
      name: 'email',
      type: 'email',
      label: 'Email Address',
      required: true,
      tab: 'Basic Info',
      schema: z.string()
        .email('Must be a valid email')
        .endsWith('@company.com', 'Must use company email domain'),
    },

    // Account Tab
    {
      name: 'username',
      type: 'text',
      label: 'Username',
      required: true,
      tab: 'Account',
      schema: z.string()
        .min(3)
        .max(20)
        .regex(/^[a-z0-9_]+$/, 'Only lowercase letters, numbers, and underscores'),
    },
    {
      name: 'password',
      type: 'password_generate',
      label: 'Password',
      required: true,
      tab: 'Account',
      helpText: 'Click Generate for a secure random password',
      onPasswordGenerated: (pwd) => setGeneratedPassword(pwd),
    },

    // Preferences Tab
    {
      name: 'role',
      type: 'select',
      label: 'Role',
      required: true,
      tab: 'Preferences',
      options: [
        { value: 'admin', label: 'Administrator' },
        { value: 'maintainer', label: 'Maintainer' },
        { value: 'viewer', label: 'Viewer' },
      ],
    },
    {
      name: 'enableNotifications',
      type: 'checkbox',
      label: 'Enable Email Notifications',
      defaultValue: true,
      tab: 'Preferences',
    },
    {
      name: 'notificationEmail',
      type: 'email',
      label: 'Notification Email',
      tab: 'Preferences',
      triggerField: 'enableNotifications',
      helpText: 'Leave blank to use primary email',
    },

    // Advanced Tab - Only for admins
    {
      name: 'allowedDomains',
      type: 'multiline',
      label: 'Allowed Domains',
      rows: 5,
      tab: 'Advanced',
      showWhen: (values) => values.role === 'admin',
      placeholder: 'example.com\nanother-domain.com',
      helpText: 'Enter one domain per line',
    },

    // Documents Tab
    {
      name: 'avatar',
      type: 'file',
      label: 'Profile Picture',
      tab: 'Documents',
      accept: 'image/*',
      maxFileSize: 5 * 1024 * 1024,  // 5MB
      helpText: 'Upload a profile picture (max 5MB)',
    },
    {
      name: 'documents',
      type: 'file_multiple',
      label: 'Verification Documents',
      tab: 'Documents',
      accept: '.pdf,.doc,.docx',
      maxFileSize: 10 * 1024 * 1024,  // 10MB per file
      maxFiles: 3,
      helpText: 'Upload up to 3 documents (max 10MB each)',
    },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Form data:', data);
    console.log('Generated password:', generatedPassword);

    // Handle file uploads
    if (data.avatar) {
      console.log('Avatar file:', data.avatar.name);
    }
    if (data.documents && data.documents.length > 0) {
      console.log('Documents:', data.documents.map((f: File) => f.name));
    }

    // Handle multiline array
    if (data.allowedDomains) {
      console.log('Allowed domains:', data.allowedDomains);  // string[]
    }

    // Make API call
    await fetch('/api/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  };

  return (
    <>
      <button onClick={() => setIsOpen(true)}>Register New User</button>
      <FormModalBuilder
        title="User Registration"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        width="xl"
        // Auto-tabbed by tab property in fields
      />
    </>
  );
}
```

### File Upload Example

```tsx
const fileUploadFields: FormField[] = [
  {
    name: 'logo',
    type: 'file',
    label: 'Company Logo',
    required: true,
    accept: 'image/png,image/jpeg,image/svg+xml',
    maxFileSize: 2 * 1024 * 1024,  // 2MB
    helpText: 'PNG, JPG, or SVG (max 2MB)',
  },
  {
    name: 'attachments',
    type: 'file_multiple',
    label: 'Supporting Documents',
    accept: '.pdf',
    maxFileSize: 10 * 1024 * 1024,  // 10MB per file
    maxFiles: 5,
    helpText: 'Upload up to 5 PDF files (max 10MB each)',
  },
];
```

### Multiline Array Example

```tsx
const multilineFields: FormField[] = [
  {
    name: 'emailList',
    type: 'multiline',
    label: 'Email Recipients',
    rows: 10,
    placeholder: 'user1@example.com\nuser2@example.com\nuser3@example.com',
    helpText: 'Enter one email address per line',
    schema: z.string()
      .transform((str) => str.split('\n').filter(Boolean))
      .pipe(z.array(z.string().email('Each line must be a valid email'))),
  },
];

// On submit, data.emailList will be: string[] = ['user1@example.com', 'user2@example.com', ...]
```

### Conditional Fields Example

```tsx
const conditionalFields: FormField[] = [
  {
    name: 'accountType',
    type: 'select',
    label: 'Account Type',
    required: true,
    options: [
      { value: 'personal', label: 'Personal' },
      { value: 'business', label: 'Business' },
      { value: 'enterprise', label: 'Enterprise' },
    ],
  },
  {
    name: 'companyName',
    type: 'text',
    label: 'Company Name',
    required: true,
    showWhen: (values) => values.accountType === 'business' || values.accountType === 'enterprise',
  },
  {
    name: 'taxId',
    type: 'text',
    label: 'Tax ID',
    required: true,
    showWhen: (values) => values.accountType === 'business' || values.accountType === 'enterprise',
  },
  {
    name: 'customDomain',
    type: 'text',
    label: 'Custom Domain',
    showWhen: (values) => values.accountType === 'enterprise',
    helpText: 'Enterprise feature only',
  },
];
```

### Complete Examples in Repository

See the `examples/` directory for complete working examples:

- `TabbedFormExample.tsx` - Auto-tabbed forms, manual tabs, explicit tabs
- `ThemedFormExample.tsx` - Dark mode, light mode, purple/pink, emerald themes
- `SidebarMenuExample.tsx` - Elder, navy/gold, emerald, light themes

## Validation

### Built-in Zod Validators

The FormModalBuilder uses Zod for type-safe validation with automatic validators for each field type:

- **Email**: RFC-compliant email validation (`z.string().email()`)
- **URL**: Valid URL format check (`z.string().url()`)
- **Number**: Min/max range validation (`z.number().min().max()`)
- **Tel**: Phone number pattern (`z.string().regex(/^[\d\s\-+()]+$/)`)
- **Date**: YYYY-MM-DD format (`z.string().regex(/^\d{4}-\d{2}-\d{2}$/)`)
- **Time**: HH:mm format (`z.string().regex(/^\d{2}:\d{2}/)`)
- **Password**: Minimum 8 characters (`z.string().min(8)`)
- **Required**: Non-empty field validation (automatic for `required: true`)

### Custom Zod Schemas

Add custom validation with Zod schemas for powerful, type-safe validation:

```tsx
import { z } from '@penguintechinc/react-libs';

{
  name: 'username',
  type: 'text',
  label: 'Username',
  schema: z.string()
    .min(3, 'Username must be at least 3 characters')
    .max(20, 'Username must be at most 20 characters')
    .regex(/^[a-z0-9_]+$/, 'Only lowercase letters, numbers, and underscores allowed')
    .refine(
      async (val) => {
        // Async validation - check if username is available
        const response = await fetch(`/api/check-username/${val}`);
        return response.ok;
      },
      'Username is already taken'
    ),
}
```

**Advanced Zod Examples:**

```tsx
// Email with domain restriction
{
  name: 'workEmail',
  type: 'email',
  label: 'Work Email',
  schema: z.string()
    .email('Must be a valid email')
    .endsWith('@company.com', 'Must use company email'),
}

// Number with custom range
{
  name: 'percentage',
  type: 'number',
  label: 'Percentage',
  schema: z.number()
    .min(0, 'Cannot be negative')
    .max(100, 'Cannot exceed 100'),
}

// String transformation and validation
{
  name: 'slug',
  type: 'text',
  label: 'URL Slug',
  schema: z.string()
    .transform((val) => val.toLowerCase().replace(/\s+/g, '-'))
    .regex(/^[a-z0-9-]+$/, 'Invalid slug format'),
}
```

### Legacy Custom Validators (Deprecated)

The older `validation` prop is still supported but deprecated in favor of Zod schemas:

```tsx
{
  name: 'username',
  type: 'text',
  label: 'Username',
  validation: (value) => {
    if (value.length < 3) return 'Too short';
    if (value.length > 20) return 'Too long';
    return null;  // null = valid
  }
}
```

**Note:** Use Zod schemas (`schema` prop) for new code. The `validation` prop will be removed in a future version.

## Styling

The components use Tailwind CSS classes. Required dependencies:

```json
{
  "dependencies": {
    "tailwindcss": "^3.0.0"
  }
}
```

Ensure your `tailwind.config.js` includes the component paths:

```js
module.exports = {
  content: [
    './src/**/*.{js,jsx,ts,tsx}',
    './node_modules/@penguintechinc/react-libs/**/*.{js,jsx,ts,tsx}',
  ],
  // ...
};
```

## Accessibility

Both components follow accessibility best practices:

- **ARIA attributes**: Proper `role`, `aria-labelledby`, `aria-modal`
- **Keyboard navigation**: Tab through fields, Escape to close
- **Screen readers**: Descriptive labels and error messages
- **Focus management**: Auto-focus on first field

## TypeScript Support

Full TypeScript support with exported types and utilities:

```typescript
import type {
  // FormModalBuilder types
  FormField,
  FormTab,
  FormModalBuilderProps,
  ColorConfig,

  // SidebarMenu types
  MenuItem,
  MenuCategory,
  SidebarMenuProps,
  SidebarColorConfig,
} from '@penguintechinc/react-libs';

// Utilities
import { generatePassword, z } from '@penguintechinc/react-libs';
```

**Available Exports:**
- `FormModalBuilder` - React component
- `SidebarMenu` - React component
- `generatePassword()` - Password generation utility
- `z` - Zod validation library (re-exported for convenience)
- All TypeScript interfaces and types

## License

AGPL-3.0 - See LICENSE file for details

## Support

For issues and questions:
- GitHub: https://github.com/penguintechinc/project-template/issues
- Email: dev@penguintech.io
