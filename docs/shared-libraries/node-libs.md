# @penguin/node_libs - Node.js/TypeScript Shared Library

Modern TypeScript library providing secure, reusable components for validation, security, cryptography, and more. Designed for Express.js applications with full type safety and ESM support.

**License**: GNU Affero General Public License v3 (AGPL-3.0)
**Node.js**: 18.0.0+
**Status**: Stable (v1.0.0)

## Installation

```bash
npm install @penguin/node_libs
```

## Features

### Validation (PyDAL-style)

Input validators with chainable API and full TypeScript support:

```typescript
import { chain, notEmpty, length, email } from '@penguin/node_libs/validation';

// Single validator
const emailValidator = email();
const result = emailValidator("user@example.com");
if (!result.isValid) {
  console.error("Validation error:", result.error);
  return;
}

// Chained validators
const validator = chain(
  notEmpty(),
  length(3, 255),
  email()
);

const result = validator("user@example.com");
if (result.isValid) {
  console.log("Valid email:", result.value);
}

// Strong password validation
import { strongPassword, PasswordOptions } from '@penguin/node_libs/validation';

const passwordValidator = strongPassword({
  minLength: 12,
  requireSpecial: true,
});

const pwResult = passwordValidator("SecureP@ss123!");
```

#### Available Validators

**String Validators:**
- `notEmpty()` - Non-empty/non-whitespace strings
- `length(min, max)` - Length constraints
- `minLength(min)` - Minimum length
- `maxLength(max)` - Maximum length
- `match(pattern)` - Regex pattern matching
- `alphanumeric(options)` - Alphanumeric only
- `slug()` - URL-safe slugs
- `isIn(options)` - Membership in set
- `trimmed()` - Trim whitespace

**Numeric Validators:**
- `isInt()` - Integer type validation
- `isFloat()` - Float type validation
- `intInRange(min, max)` - Integer range
- `floatInRange(min, max)` - Float range
- `isPositive()` - Positive numbers
- `isNegative()` - Negative numbers

**Network Validators:**
- `email()` - Email format validation
- `url()` - URL format validation
- `ipAddress()` - IPv4/IPv6 validation
- `hostname()` - Hostname validation

**DateTime Validators:**
- `date(format?)` - Date format validation
- `datetime(format?)` - DateTime format validation
- `time(format?)` - Time format validation
- `dateInRange(start, end)` - Date range

**Password Validators:**
- `strongPassword(options?)` - Configurable password strength
- Presets: weak, moderate, strong, enterprise

### Security

Security utilities for Express.js applications:

```typescript
import express from 'express';
import {
  secureHeaders,
  rateLimit,
  csrfProtection,
  sanitizeInput
} from '@penguin/node_libs/security';

const app = express();

// Add secure headers middleware
app.use(secureHeaders());

// Rate limiting (100 requests per 60 seconds)
app.use(rateLimit({
  maxRequests: 100,
  windowSeconds: 60,
  store: 'memory' // or 'redis'
}));

// CSRF protection
app.use(csrfProtection());

// Protected endpoint
app.post('/api/v1/data', (req, res) => {
  // Sanitize user input
  const rawInput = req.body.data;
  const safeInput = sanitizeInput(rawInput);

  res.json({ processed: safeInput });
});

app.listen(3000);
```

**Available Security Functions:**
- `sanitizeInput(input)` - XSS/HTML sanitization
- `escapeSQL(input)` - SQL parameter escaping
- `secureHeaders()` - Middleware for secure HTTP headers
- `rateLimit(options)` - Rate limiting middleware
- `csrfProtection()` - CSRF token validation
- `auditLog(action, details)` - Audit logging

### Cryptography

Modern cryptographic operations:

```typescript
import {
  hashPassword,
  verifyPassword,
  encryptChaCha20,
  decryptChaCha20,
  generateToken
} from '@penguin/node_libs/crypto';

// Password hashing (Argon2)
const password = "user_password";
const hash = await hashPassword(password);

// Password verification
const isValid = await verifyPassword(password, hash);
console.log("Valid:", isValid); // true

// Encryption (ChaCha20-Poly1305)
const key = Buffer.from("32-byte-encryption-key-here----");
const plaintext = "Sensitive data";

const { ciphertext, nonce } = await encryptChaCha20(plaintext, key);

// Decryption
const decrypted = await decryptChaCha20(ciphertext, nonce, key);
console.log("Decrypted:", decrypted);

// Secure token generation
const token = await generateToken(32);
console.log("Token:", token);

// JWT operations
import { generateJWT, verifyJWT } from '@penguin/node_libs/crypto';

const payload = { userId: 123, email: "user@example.com" };
const jwtToken = await generateJWT(payload, "secret-key");

const verified = await verifyJWT(jwtToken, "secret-key");
console.log("User ID:", verified.userId);
```

**Cryptographic Functions:**
- `hashPassword(password)` - Argon2 hashing
- `verifyPassword(password, hash)` - Password verification
- `encryptChaCha20(plaintext, key)` - ChaCha20-Poly1305 encryption
- `decryptChaCha20(ciphertext, nonce, key)` - ChaCha20-Poly1305 decryption
- `encryptAES(plaintext, key)` - AES-256-GCM encryption
- `decryptAES(ciphertext, key)` - AES-256-GCM decryption
- `generateToken(length)` - Cryptographically secure random token
- `generateJWT(payload, secret)` - JWT creation
- `verifyJWT(token, secret)` - JWT validation

### HTTP Client

Resilient HTTP client with correlation IDs and retries:

```typescript
import { createHttpClient } from '@penguin/node_libs/http';

// Create HTTP client with retries
const client = createHttpClient({
  baseURL: 'https://api.example.com',
  timeout: 10000,
  maxRetries: 3,
  backoffFactor: 0.5,
});

// Make requests with automatic retries
const response = await client.get('/users/123');
const data = response.data;

// With correlation ID
const clientWithCorr = createHttpClient({
  baseURL: 'https://api.example.com',
  withCorrelationID: true,
});

const response = await clientWithCorr.post(
  '/events',
  { type: 'user_login' }
);

// Streaming responses
const stream = await client.stream('GET', '/large-file');
stream.pipe(fs.createWriteStream('output.bin'));
```

**HTTP Client Features:**
- Automatic retries with exponential backoff
- Correlation ID propagation for request tracking
- Connection pooling
- Timeout handling
- Stream support
- Type-safe response handling

### gRPC Integration

Production-ready gRPC server setup:

```typescript
import {
  createSecureServer,
  addAuthInterceptor
} from '@penguin/node_libs/grpc';
import * as protoLoader from '@grpc/proto-loader';

const packageDefinition = protoLoader.loadSync('service.proto', {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const serviceProto = grpc.loadPackageDefinition(packageDefinition);

const server = await createSecureServer({
  port: 50051,
  certFile: '/path/to/cert.pem',
  keyFile: '/path/to/key.pem',
});

// Add authentication interceptor
server.addInterceptor(
  addAuthInterceptor({ token: 'secret' })
);

await server.start();
```

**gRPC Features:**
- TLS/SSL support
- Authentication interceptors
- Error handling
- Metadata propagation
- Streaming support

## Quick Start Examples

### Express Application with Validation

```typescript
import express from 'express';
import { chain, notEmpty, length, email } from '@penguin/node_libs/validation';

const app = express();
app.use(express.json());

// Email validators
const emailValidator = chain(
  notEmpty(),
  length(3, 255),
  email()
);

app.post('/api/v1/users', (req, res) => {
  const { email: rawEmail } = req.body;

  // Validate email
  const result = emailValidator(rawEmail);
  if (!result.isValid) {
    return res.status(400).json({ error: result.error });
  }

  // Use validated email
  const validEmail = result.value;
  res.status(201).json({ email: validEmail, id: 123 });
});

app.listen(3000);
```

### Custom Validator

```typescript
import { type Validator, success, failure } from '@penguin/node_libs/validation';

/**
 * Validates US phone numbers in format (XXX) XXX-XXXX
 */
function phoneNumber(): Validator<string, string> {
  const pattern = /^\(\d{3}\)\s\d{3}-\d{4}$/;

  return (value: string) => {
    if (typeof value !== 'string') {
      return failure('Must be a string');
    }

    if (!pattern.test(value)) {
      return failure('Invalid phone format');
    }

    return success(value);
  };
}

// Usage
const validator = phoneNumber();
const result = validator("(555) 123-4567");
console.log(result.isValid); // true
```

### API Request Validation with Multiple Fields

```typescript
import express from 'express';
import {
  chain,
  notEmpty,
  email,
  length,
  strongPassword
} from '@penguin/node_libs/validation';

interface UserRegistration {
  email: string;
  password: string;
  username: string;
}

interface ValidationErrors {
  email?: string;
  password?: string;
  username?: string;
}

// Field validators
const emailValidator = chain(notEmpty(), email());
const passwordValidator = strongPassword();
const usernameValidator = chain(
  notEmpty(),
  length(3, 30)
);

function validateRegistration(data: unknown): ValidationErrors | null {
  if (typeof data !== 'object' || data === null) {
    return { email: 'Invalid request' };
  }

  const obj = data as Record<string, unknown>;
  const errors: ValidationErrors = {};

  // Validate email
  const emailResult = emailValidator(obj.email);
  if (!emailResult.isValid) {
    errors.email = emailResult.error ?? 'Invalid email';
  }

  // Validate password
  const passwordResult = passwordValidator(obj.password);
  if (!passwordResult.isValid) {
    errors.password = passwordResult.error ?? 'Invalid password';
  }

  // Validate username
  const usernameResult = usernameValidator(obj.username);
  if (!usernameResult.isValid) {
    errors.username = usernameResult.error ?? 'Invalid username';
  }

  // Return null if no errors
  if (Object.keys(errors).length === 0) {
    return null;
  }

  return errors;
}

const app = express();
app.use(express.json());

app.post('/api/v1/register', (req, res) => {
  const validationErrors = validateRegistration(req.body);

  if (validationErrors) {
    return res.status(400).json(validationErrors);
  }

  res.status(201).json({ message: 'User created' });
});

app.listen(3000);
```

### TypeScript Types

All validators are fully typed:

```typescript
import {
  type ValidationResult,
  type Validator,
  chain,
  notEmpty,
  email,
  unwrap,
  unwrapOr
} from '@penguin/node_libs/validation';

// Typed validators
const emailValidator: Validator<string, string> = email();

// Typed result
const result: ValidationResult<string> = emailValidator("user@example.com");

// Type-safe unwrapping
if (result.isValid) {
  const email: string = unwrap(result);
}

// Default value
const fallback: string = unwrapOr(result, "no-email@example.com");
```

## Configuration

### Environment Variables

```bash
# Security
NODE_LIBS_SECURE_HEADERS=true
NODE_LIBS_RATE_LIMIT_STORE=redis
NODE_LIBS_RATE_LIMIT_REDIS_URL=redis://localhost:6379

# Crypto
NODE_LIBS_ENCRYPTION_KEY=your-32-byte-key-here

# gRPC
NODE_LIBS_GRPC_CERT_FILE=/path/to/cert.pem
NODE_LIBS_GRPC_KEY_FILE=/path/to/key.pem
```

## Development

### Setup

```bash
# Install dependencies
npm install

# Install with dev dependencies
npm install --save-dev
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test:watch
```

### Code Quality

```bash
# Format code
npm run format

# Linting
npm run lint

# Fix linting issues
npm run lint:fix

# Type checking
npm run typecheck

# Run all checks
./scripts/lint.sh
```

### Building

```bash
# Build TypeScript to JavaScript
npm run build

# Watch mode for development
npm run build:watch

# Clean build artifacts
npm run clean
```

## Performance

### Optimization Tips

1. **Reuse Validators**: Create validators once and reuse them
   ```typescript
   const emailValidator = email();  // Create once
   // Then use many times
   const result1 = emailValidator("user1@example.com");
   const result2 = emailValidator("user2@example.com");
   ```

2. **Reuse HTTP Client**: Connection pooling
   ```typescript
   const client = createHttpClient({
     baseURL: 'https://api.example.com',
   });
   // Use same client for multiple requests
   const res1 = await client.get('/data/1');
   const res2 = await client.get('/data/2');
   ```

3. **Async Operations**: Leverage async/await
   ```typescript
   const results = await Promise.all([
     client.get('/users/1'),
     client.get('/users/2'),
     client.get('/users/3'),
   ]);
   ```

4. **Stream Large Responses**: For large data
   ```typescript
   const stream = await client.stream('GET', '/large-file');
   stream.pipe(fs.createWriteStream('output.bin'));
   ```

## Common Issues

### Module not found errors

**Solution**: Ensure library is installed correctly:
```bash
npm install @penguin/node_libs
npm install --save-dev  # For dev dependencies
```

### TypeScript errors

**Solution**: Build and check types:
```bash
npm run build
npm run typecheck
```

### Crypto import errors

**Solution**: Install peer dependencies:
```bash
npm install argon2
```

### gRPC import errors

**Solution**: Install optional peer dependencies:
```bash
npm install @grpc/grpc-js @grpc/proto-loader
```

## Browser Compatibility

This library is designed for Node.js and is NOT compatible with browsers.

For browser-based applications, use client-side validation libraries.

## ESM/CommonJS Support

This library uses ES Modules (ESM) exclusively:

```typescript
// ✅ Supported
import { email } from '@penguin/node_libs/validation';

// ❌ Not supported
const { email } = require('@penguin/node_libs/validation');
```

Ensure your `package.json` includes:
```json
{
  "type": "module",
  "exports": {
    ".": "./dist/index.js"
  }
}
```

## License

GNU Affero General Public License v3 (AGPL-3.0)

This library is part of the Penguin Tech Inc project template. See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/penguintechinc/project-template/issues
- Documentation: https://docs.penguintech.io/node-libs
- Email: dev@penguintech.io

## See Also

- [Shared Libraries Overview](./overview.md)
- [Python Library](./py-libs.md)
- [Go Library](./go-libs.md)
