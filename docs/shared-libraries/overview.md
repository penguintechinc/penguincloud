# Penguin Libraries (`penguin-libs`)

Shared libraries for Penguin Tech applications across all ecosystems. All packages live in the [`penguin-libs`](https://github.com/penguintechinc/penguin-libs) monorepo at `~/code/penguin-libs`.

> **Repository**: `github.com/penguintechinc/penguin-libs`
> **License**: AGPL-3.0

## Available Packages

| Package | Ecosystem | Version | Status | Install |
|---------|-----------|---------|--------|---------|
| `@penguintechinc/react-libs` | React/TypeScript | 1.1.1 | Stable | `npm install @penguintechinc/react-libs` |
| `penguin-utils` | Python 3.11+ | 0.1.0 | Alpha | `pip install penguin-utils` |
| `go-common` | Go 1.24 | — | Alpha | `go get github.com/penguintechinc/penguin-libs/packages/go-common` |
| `flutter_libs` | Dart/Flutter | 0.1.0 | Alpha | Git dependency (see [flutter-libs.md](./flutter-libs.md)) |

## Repository Structure

```
~/code/penguin-libs/
├── packages/
│   ├── react-libs/          # @penguintechinc/react-libs (npm, GitHub Packages)
│   │   ├── src/
│   │   │   └── components/  # LoginPageBuilder, FormBuilder, FormModalBuilder, SidebarMenu, ConsoleVersion
│   │   ├── examples/
│   │   ├── package.json
│   │   └── tsconfig.json
│   ├── python-utils/        # penguin-utils (PyPI, import as penguintechinc_utils)
│   │   ├── src/
│   │   │   └── penguintechinc_utils/
│   │   │       └── logging.py   # SanitizedLogger, sanitize_log_data, get_logger
│   │   └── pyproject.toml
│   ├── go-common/           # Go module
│   │   ├── logging/
│   │   │   └── sanitize.go  # SanitizedLogger, SanitizeValue, SanitizeFields
│   │   └── go.mod
│   └── flutter_libs/        # flutter_libs (Dart/Flutter, git dependency)
│       ├── lib/
│       └── pubspec.yaml
├── .github/workflows/       # Automated publishing
├── package.json             # Workspace root
└── README.md
```

---

## React — `@penguintechinc/react-libs`

UI components for all React web applications. **Mandatory** for every project with a WebUI.

### Installation

```bash
# One-time: configure npm for GitHub Packages
echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc

# Install
npm install @penguintechinc/react-libs
```

For CI/CD (GitHub Actions):
```yaml
- name: Configure npm for GitHub Packages
  run: echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### What It Provides

| Component | Purpose |
|-----------|---------|
| `LoginPageBuilder` | Full login page with MFA, CAPTCHA (ALTCHA), social login (OAuth2/OIDC/SAML), GDPR consent |
| `FormBuilder` | Flexible form component supporting both inline and modal modes, 13+ field types, validation |
| `FormModalBuilder` | Dynamic modal forms with auto-tabbing, 16+ field types, Zod validation, file upload |
| `SidebarMenu` | Collapsible sidebar navigation with role-based visibility, theming |
| `AppConsoleVersion` | Logs WebUI + API version info to browser console on startup |
| `ConsoleVersion` | Lower-level version logging utility |

**Hooks**: `useVersionInfo`, `useApiVersionInfo`, `useCaptcha`, `useCookieConsent`, `useFormBuilder`

**Utilities**: `generatePassword`, `buildOAuth2Url`, `buildOIDCUrl`, `buildSAMLRequest`, `generateState`, `validateState`

### Usage

```tsx
import {
  LoginPageBuilder,
  FormModalBuilder,
  SidebarMenu,
  AppConsoleVersion,
} from '@penguintechinc/react-libs';

// Login page with MFA + CAPTCHA
<LoginPageBuilder
  api={{ loginUrl: '/api/v1/auth/login' }}
  branding={{ appName: 'My App', githubRepo: 'penguintechinc/my-app' }}
  onSuccess={(response) => {
    localStorage.setItem('authToken', response.token);
    window.location.href = '/dashboard';
  }}
  gdpr={{ enabled: true, privacyPolicyUrl: '/privacy' }}
  mfa={{ enabled: true, codeLength: 6 }}
  captcha={{ enabled: true, provider: 'altcha', challengeUrl: '/api/v1/captcha/challenge' }}
/>

// Form modal
<FormModalBuilder
  title="Create User"
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  fields={[
    { name: 'email', type: 'email', label: 'Email', required: true },
    { name: 'role', type: 'select', label: 'Role', options: [
      { value: 'admin', label: 'Admin' },
      { value: 'viewer', label: 'Viewer' },
    ]},
  ]}
/>

// Version logging (place in App.tsx)
<AppConsoleVersion
  appName="My App"
  webuiVersion={import.meta.env.VITE_VERSION || '0.0.0'}
  webuiBuildEpoch={Number(import.meta.env.VITE_BUILD_TIME) || 0}
  environment={import.meta.env.MODE}
  apiStatusUrl="/api/v1/status"
/>

// Sidebar navigation
<SidebarMenu
  logo={<img src="/logo.png" alt="Logo" />}
  categories={[
    { header: 'Main', items: [
      { name: 'Dashboard', href: '/', icon: HomeIcon },
      { name: 'Users', href: '/users', icon: UsersIcon },
    ]},
  ]}
  currentPath={location.pathname}
  onNavigate={(href) => navigate(href)}
  userRole="admin"
/>
```

### Peer Dependencies

Requires `react >= 18.0.0` and `react-dom >= 18.0.0`. Ships with `zod` for validation.

📚 **Full docs**: [react-libs.md](./react-libs.md)

---

## Python — `penguin-utils`

Shared utilities for Python applications. Currently provides sanitized logging.

### Installation

```bash
# Basic
pip install penguin-utils

# With Flask integration
pip install penguin-utils[flask]

# For development
pip install penguin-utils[dev]
```

Requires Python 3.11+ (3.13 recommended). Depends on `pydal >= 20230521.1`.

### What It Provides

| Module | Purpose |
|--------|---------|
| `logging.SanitizedLogger` | Logger that auto-redacts passwords, tokens, emails, MFA codes, session IDs |
| `logging.sanitize_log_data()` | Sanitize a dict for safe logging (redacts sensitive keys, masks emails to domain only) |
| `logging.get_logger()` | Get a pre-formatted logger with `[name] LEVEL: message` format |

**Redacted keys**: `password`, `secret`, `token`, `api_key`, `auth_token`, `access_token`, `refresh_token`, `credential`, `mfa_code`, `totp_code`, `otp`, `captcha_token`, `session_id`, `cookie`, `authorization` (and substrings)

**Email handling**: Emails are masked to domain only — `user@example.com` becomes `[email]@example.com`

### Usage

```python
from penguintechinc_utils import get_logger, sanitize_log_data
from penguintechinc_utils.logging import SanitizedLogger

# Simple formatted logger
logger = get_logger("MyService")
logger.info("Service started")
# Output: [MyService] INFO: Service started

# Sanitized logger (auto-redacts sensitive data)
log = SanitizedLogger("AuthService")

log.info("Login attempt", {
    "email": "user@example.com",
    "password": "secret123",
    "remember_me": True,
})
# Output: [AuthService] INFO: Login attempt {'email': '[email]@example.com', 'password': '[REDACTED]', 'remember_me': True}

log.warning("Token refresh failed", {
    "user_id": 42,
    "auth_token": "eyJhbGciOiJI...",
})
# Output: [AuthService] WARNING: Token refresh failed {'user_id': 42, 'auth_token': '[REDACTED]'}

# Standalone sanitization (for custom logging setups)
raw_data = {"email": "admin@company.com", "api_key": "sk-12345", "action": "login"}
safe_data = sanitize_log_data(raw_data)
# {'email': '[email]@company.com', 'api_key': '[REDACTED]', 'action': 'login'}
```

### Integration with Flask

```python
from penguintechinc_utils.logging import SanitizedLogger

log = SanitizedLogger("FlaskApp")

@app.before_request
def log_request():
    log.info("Request", {
        "method": request.method,
        "path": request.path,
        "authorization": request.headers.get("Authorization", ""),
    })
    # 'authorization' is auto-redacted
```

📚 **Full docs**: [py-libs.md](./py-libs.md)

---

## Go — `go-common`

Shared utilities for Go services. Currently provides sanitized logging built on `uber/zap`.

### Installation

```bash
go get github.com/penguintechinc/penguin-libs/packages/go-common
```

Requires Go 1.24. Depends on `go.uber.org/zap v1.27.0`.

### What It Provides

| Symbol | Purpose |
|--------|---------|
| `logging.NewSanitizedLogger(name)` | Create a zap logger that auto-redacts sensitive fields |
| `logging.SanitizeValue(key, value)` | Redact a single value if the key is sensitive |
| `logging.SanitizeFields(fields)` | Redact a slice of `zap.Field` entries |
| `logging.SanitizeField(field)` | Redact a single `zap.Field` |
| `logging.SensitiveKeys` | Map of key names that trigger redaction |

Same redaction rules as the Python package — same sensitive keys, same email masking to domain only.

### Usage

```go
package main

import (
    "github.com/penguintechinc/penguin-libs/packages/go-common/logging"
    "go.uber.org/zap"
)

func main() {
    // Create a sanitized logger
    log, err := logging.NewSanitizedLogger("AuthService")
    if err != nil {
        panic(err)
    }
    defer log.Sync()

    // Sensitive fields are auto-redacted
    log.Info("Login attempt",
        zap.String("email", "user@example.com"),
        zap.String("password", "secret123"),
        zap.Bool("remember_me", true),
    )
    // Output: {"level":"info","logger":"AuthService","msg":"Login attempt",
    //          "email":"[email]@example.com","password":"[REDACTED]","remember_me":true}

    log.Warn("Token refresh failed",
        zap.Int("user_id", 42),
        zap.String("auth_token", "eyJhbGciOiJI..."),
    )
    // auth_token is auto-redacted

    // Standalone sanitization
    sanitized := logging.SanitizeValue("api_key", "sk-12345")
    // Returns: "[REDACTED]"

    emailSanitized := logging.SanitizeValue("email", "admin@company.com")
    // Returns: "[email]@company.com"
}
```

### Integration with HTTP handlers

```go
func authHandler(w http.ResponseWriter, r *http.Request) {
    log.Info("Auth request",
        zap.String("method", r.Method),
        zap.String("path", r.URL.Path),
        zap.String("authorization", r.Header.Get("Authorization")),
    )
    // 'authorization' is auto-redacted
}
```

📚 **Full docs**: [go-libs.md](./go-libs.md)

---

## Flutter — `flutter_libs`

Shared Flutter widgets and utilities for Penguin Tech mobile applications. Located at `packages/flutter_libs/` in the monorepo.

### Installation

```yaml
# pubspec.yaml
dependencies:
  flutter_libs:
    git:
      url: https://github.com/penguintechinc/penguin-libs.git
      path: packages/flutter_libs
      ref: main
```

### What It Provides

- Elder dark/gold theme data
- Form widgets and validation
- Login components
- Sidebar navigation
- Console version logging
- Adaptive layout utilities (phone vs tablet)

📚 **Full docs**: [flutter-libs.md](./flutter-libs.md)
📚 **Mobile standards**: [MOBILE.md](../standards/MOBILE.md)

---

## Cross-Library Consistency

All packages in the monorepo follow the same patterns:

### Sanitized Logging (Python + Go)

Both languages implement identical redaction rules:
- Same set of sensitive keys (`password`, `token`, `api_key`, `mfa_code`, etc.)
- Same email masking (`user@example.com` → `[email]@example.com`)
- Same `SanitizedLogger` class with `debug`, `info`, `warning`/`warn`, `error` methods
- Nested dict/object sanitization (recursive)

### Console Version Logging (React)

The `AppConsoleVersion` component logs build info to the browser console. All React apps must include it. When the Flutter package is created, it will provide an equivalent `PenguinConsoleVersion` utility.

### UI Components (React)

Login, forms, navigation, and theming are standardized through the React library. The same design tokens (dark/gold palette, slate backgrounds, amber accents) should be applied across all platforms.

## Development

### Working on the Libraries

```bash
# Clone the monorepo
git clone https://github.com/penguintechinc/penguin-libs.git
cd penguin-libs

# React
npm install
npm run build:react-libs
cd packages/react-libs && npm run lint

# Python
cd packages/python-utils
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/

# Go
cd packages/go-common
go test ./...
```

### Publishing

React packages publish automatically via GitHub Actions on version tags. Manual publish:

```bash
cd packages/react-libs
npm version patch   # or minor, major
npm publish
```

Python and Go packages follow their respective ecosystem publishing workflows.

## Support

- GitHub: https://github.com/penguintechinc/penguin-libs/issues
- Email: dev@penguintech.io
- Homepage: https://www.penguintech.io
