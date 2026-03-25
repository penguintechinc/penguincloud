# py_libs - Python Shared Library

Enterprise-grade Python library providing secure, reusable components for validation, security, cryptography, and more. Designed for Flask applications with full type hints and async support.

**License**: GNU Affero General Public License v3 (AGPL-3.0)
**Python**: 3.12+
**Status**: Stable (v1.0.0)

## Installation

### Basic Installation

```bash
pip install -e .
```

### With Optional Dependencies

```bash
# Flask integration only
pip install -e ".[flask]"

# gRPC support only
pip install -e ".[grpc]"

# Redis support only
pip install -e ".[redis]"

# All features (recommended for development)
pip install -e ".[all]"

# Development tools (testing, linting, type checking)
pip install -e ".[dev]"
```

## Features

### Validation (PyDAL-style)

Input validators following PyDAL's IS_* pattern with chainable API:

```python
from py_libs.validation import (
    chain, IsNotEmpty, IsLength, IsEmail,
    IsInt, IsIntInRange, IsDate,
    IsStrongPassword
)

# Single validator
email_validator = IsEmail()
result = email_validator("user@example.com")
if result.is_valid:
    email = result.unwrap()

# Chained validators
validators = chain(
    IsNotEmpty(),
    IsLength(3, 255),
    IsEmail()
)
result = validators("user@example.com")

# Strong password validation
password_validator = IsStrongPassword()
result = password_validator("SecureP@ss123!")
score = password_validator.get_strength_score("SecureP@ss123!")  # 0-100

# Custom preset
from py_libs.validation import PasswordOptions
validator = IsStrongPassword(options=PasswordOptions.enterprise())
```

#### Available Validators

**String Validators:**
- `IsNotEmpty()` - Non-empty/non-whitespace strings
- `IsLength(min, max)` - Length constraints
- `IsMatch(pattern)` - Regex pattern matching
- `IsAlphanumeric(allow_underscore=False, allow_dash=False)` - Alphanumeric only
- `IsSlug()` - URL-safe slugs
- `IsIn(options, case_sensitive=True)` - Membership in set
- `IsTrimmed(allow_empty=False)` - Trim and validate

**Numeric Validators:**
- `IsInt()` - Integer type validation
- `IsFloat()` - Float type validation
- `IsIntInRange(min, max)` - Integer range
- `IsFloatInRange(min, max)` - Float range
- `IsPositive()` - Positive numbers
- `IsNegative()` - Negative numbers

**Network Validators:**
- `IsEmail()` - Email format validation
- `IsURL()` - URL format validation
- `IsIPAddress()` - IPv4/IPv6 validation
- `IsHostname()` - Hostname validation

**DateTime Validators:**
- `IsDate()` - Date format validation
- `IsDateTime()` - DateTime format validation
- `IsTime()` - Time format validation
- `IsDateInRange(start, end)` - Date range

**Password Validators:**
- `IsStrongPassword(options)` - Configurable password strength
- `PasswordOptions` - Presets: weak, moderate, strong, enterprise

### Security

Security utilities for Flask applications:

```python
from flask import Flask, request
from py_libs.security import (
    sanitize_input, secure_headers_middleware,
    rate_limit, csrf_protection
)

app = Flask(__name__)

# Add secure headers
app.before_request(secure_headers_middleware)

# Rate limiting
limiter = rate_limit(max_requests=100, window_seconds=60)

@app.route("/api/v1/data")
@limiter
def protected_endpoint():
    # Sanitize user input
    user_input = request.json.get("data", "")
    safe_input = sanitize_input(user_input)
    return {"processed": safe_input}
```

**Available Security Functions:**
- `sanitize_input()` - XSS/HTML sanitization
- `escape_sql()` - SQL parameter escaping
- `secure_headers_middleware()` - Set secure HTTP headers
- `rate_limit()` - Rate limiting decorator (in-memory/Redis)
- `csrf_protection()` - CSRF token validation
- `audit_log()` - Audit logging

### Cryptography

Modern cryptographic operations:

```python
from py_libs.crypto import (
    hash_password, verify_password,
    encrypt_aes, decrypt_aes,
    generate_token
)

# Password hashing (Argon2id)
password = "user_password"
hashed = hash_password(password)
is_valid = verify_password(password, hashed)  # True

# Encryption (AES-256-GCM)
key = b"32-byte-key-for-aes-256-encryption"
plaintext = "Sensitive data"
ciphertext = encrypt_aes(plaintext, key)
decrypted = decrypt_aes(ciphertext, key)

# Secure token generation
token = generate_token(length=32)  # Random 32-byte token
```

**Cryptographic Functions:**
- `hash_password(password)` - Argon2id hashing
- `verify_password(password, hash)` - Password verification
- `hash_password_bcrypt(password)` - Bcrypt hashing (legacy)
- `verify_password_bcrypt(password, hash)` - Bcrypt verification
- `encrypt_aes(plaintext, key)` - AES-256-GCM encryption
- `decrypt_aes(ciphertext, key)` - AES-256-GCM decryption
- `generate_token(length)` - Cryptographically secure random token
- `generate_jwt(payload, secret)` - JWT creation
- `verify_jwt(token, secret)` - JWT validation

### HTTP Client

Resilient HTTP client with correlation IDs and retries:

```python
from py_libs.http import HTTPClient, CorrelationMiddleware

# Basic usage
client = HTTPClient(
    base_url="https://api.example.com",
    timeout=10,
    max_retries=3,
    backoff_factor=0.5
)

response = await client.get("/users/123")
data = response.json()

# With correlation ID for request tracking
middleware = CorrelationMiddleware()
client_with_correlation = HTTPClient(middleware=middleware)

# Correlation ID is automatically included in headers
response = await client_with_correlation.post(
    "/events",
    json={"type": "user_login"}
)
```

**HTTP Client Features:**
- Automatic retries with exponential backoff
- Correlation ID propagation for request tracking
- Connection pooling
- Timeout handling
- Session management
- Type hints for responses

### gRPC Integration

Production-ready gRPC server setup:

```python
import asyncio
from grpc import aio
from py_libs.grpc import create_secure_server, add_auth_interceptor

async def main():
    # Create secure gRPC server
    server = await create_secure_server(
        port=50051,
        cert_file="/path/to/cert.pem",
        key_file="/path/to/key.pem"
    )

    # Add authentication interceptor
    server.add_generic_rpc_interceptors(
        [add_auth_interceptor(auth_token="secret")]
    )

    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(main())
```

**gRPC Features:**
- TLS/SSL support
- Authentication interceptors
- Error handling
- Metadata propagation
- Async/await support

## Quick Start Examples

### Flask Application with Validation

```python
from flask import Flask, request, jsonify
from py_libs.validation import chain, IsNotEmpty, IsEmail, IsLength

app = Flask(__name__)

# Email validators
email_validators = chain(
    IsNotEmpty(),
    IsLength(3, 255),
    IsEmail()
)

@app.route("/api/v1/users", methods=["POST"])
def create_user():
    email = request.json.get("email", "")

    # Validate email
    result = email_validators(email)
    if not result.is_valid:
        return {"error": result.error}, 400

    # Use validated email
    validated_email = result.unwrap()
    return {"email": validated_email, "id": 123}, 201

if __name__ == "__main__":
    app.run()
```

### Custom Validator

```python
from py_libs.validation import Validator, ValidationResult

class IsPhoneNumber(Validator[str, str]):
    """Validates US phone numbers in format (XXX) XXX-XXXX"""

    def validate(self, value: str) -> ValidationResult[str]:
        import re

        if not isinstance(value, str):
            return ValidationResult.failure("Must be a string")

        pattern = r"^\(\d{3}\)\s\d{3}-\d{4}$"
        if not re.match(pattern, value):
            return ValidationResult.failure("Invalid phone format")

        return ValidationResult.success(value)

# Usage
phone_validator = IsPhoneNumber()
result = phone_validator("(555) 123-4567")
print(result.is_valid)  # True
```

### API Request Validation with Multiple Fields

```python
from dataclasses import dataclass
from py_libs.validation import (
    chain, IsNotEmpty, IsEmail,
    IsStrongPassword, IsLength
)

@dataclass
class UserRegistration:
    email: str
    password: str
    username: str

# Field validators
email_validator = chain(IsNotEmpty(), IsEmail())
password_validator = IsStrongPassword()
username_validator = chain(
    IsNotEmpty(),
    IsLength(3, 30)
)

def validate_registration(data: dict) -> dict:
    """Validate registration data and return errors"""
    errors = {}

    # Validate email
    email_result = email_validator(data.get("email", ""))
    if not email_result.is_valid:
        errors["email"] = email_result.error

    # Validate password
    password_result = password_validator(data.get("password", ""))
    if not password_result.is_valid:
        errors["password"] = password_result.error

    # Validate username
    username_result = username_validator(data.get("username", ""))
    if not username_result.is_valid:
        errors["username"] = username_result.error

    if errors:
        return {"valid": False, "errors": errors}

    return {
        "valid": True,
        "data": UserRegistration(
            email=email_result.unwrap(),
            password=password_result.unwrap(),
            username=username_result.unwrap()
        )
    }
```

## Configuration

### Environment Variables

```bash
# Logging
PY_LIBS_LOG_LEVEL=INFO

# Security
PY_LIBS_SECURE_HEADERS=true
PY_LIBS_RATE_LIMIT_REDIS_URL=redis://localhost:6379

# Crypto
PY_LIBS_ENCRYPTION_KEY=your-32-byte-key-here

# gRPC
PY_LIBS_GRPC_CERT_FILE=/path/to/cert.pem
PY_LIBS_GRPC_KEY_FILE=/path/to/key.pem
```

## Development

### Setup

```bash
# Clone and setup virtual environment
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev,all]"
```

### Running Tests

```bash
# Run all tests with coverage
python -m pytest tests/ --cov=py_libs --cov-report=html

# Run specific test file
python -m pytest tests/validation/test_validators.py -v

# Run with type checking
mypy py_libs/
```

### Code Quality

```bash
# Format code
black py_libs/
isort py_libs/

# Linting
flake8 py_libs/
ruff check py_libs/

# Security scanning
bandit -r py_libs/

# Run all linting checks
./scripts/lint.sh
```

### Type Checking

All code is fully typed. Run mypy for type checking:

```bash
mypy py_libs/ --strict
```

## Performance

### Optimization Tips

1. **Reuse Validators**: Create validators once and reuse them
   ```python
   email_validator = IsEmail()  # Create once
   # Then use many times
   result1 = email_validator("user1@example.com")
   result2 = email_validator("user2@example.com")
   ```

2. **Use Dataclasses with Slots**: Memory-efficient data structures
   ```python
   from dataclasses import dataclass

   @dataclass(slots=True)
   class User:
       id: int
       email: str
       name: str
   ```

3. **Async Operations**: Use async for I/O operations
   ```python
   from py_libs.http import HTTPClient

   client = HTTPClient()
   results = await asyncio.gather(
       client.get("/users/1"),
       client.get("/users/2"),
       client.get("/users/3")
   )
   ```

## Common Issues

### ModuleNotFoundError: No module named 'py_libs'

**Solution**: Install with `-e` flag from the correct directory:
```bash
cd shared/py_libs
pip install -e .
```

### ImportError with optional dependencies

**Solution**: Install optional dependencies:
```bash
pip install -e ".[all]"  # or specific extras [flask,grpc,redis]
```

### Type checking errors with mypy

**Solution**: Ensure you have type stubs installed:
```bash
pip install types-redis types-cryptography
```

## License

GNU Affero General Public License v3 (AGPL-3.0)

This library is part of the Penguin Tech Inc project template. See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/penguintechinc/project-template/issues
- Documentation: https://docs.penguintech.io/py-libs
- Email: dev@penguintech.io

## See Also

- [Shared Libraries Overview](./overview.md)
- [Go Library](./go-libs.md)
- [Node.js Library](./node-libs.md)
