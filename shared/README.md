# Shared Libraries

Shared libraries have been moved to the dedicated **penguin-libs** repository.

## Repository

**GitHub**: https://github.com/penguintechinc/penguin-libs

## Available Packages

### JavaScript/TypeScript (npm via GitHub Packages)

```bash
# Configure npm for @penguintechinc scope
echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc

# Install React components
npm install @penguintechinc/react-libs
```

**Components included:**
- `LoginPageBuilder` - Login page with MFA, CAPTCHA, OAuth2/OIDC/SAML, GDPR
- `FormModalBuilder` - Modal forms with validation and tabs
- `SidebarMenu` - Navigation sidebar with role-based visibility
- `AppConsoleVersion` - Build info console logging

### Python (PyPI)

```bash
pip install penguintechinc-utils
```

**Modules included:**
- `penguintechinc_utils.logging` - Sanitized logging utilities

### Go (direct import)

```bash
go get github.com/penguintechinc/penguin-libs/packages/go-common
```

**Packages included:**
- `logging` - Sanitized logging with zap

## Usage Example (React)

```tsx
import {
  LoginPageBuilder,
  FormModalBuilder,
  SidebarMenu,
  AppConsoleVersion
} from '@penguintechinc/react-libs';

// See docs/standards/REACT_LIBS.md for full documentation
```

## CI/CD Configuration

For GitHub Actions, add to your workflow:

```yaml
- name: Configure npm for GitHub Packages
  run: echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Documentation

- [React Libraries Standards](../docs/standards/REACT_LIBS.md)
- [Frontend Standards](../docs/standards/FRONTEND.md)
- [penguin-libs README](https://github.com/penguintechinc/penguin-libs)
