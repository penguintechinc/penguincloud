# go_libs - Go Shared Library

High-performance Go library providing secure, reusable components for validation, security, cryptography, and more. Designed for Gin framework applications with support for gRPC and Redis.

**License**: GNU Affero General Public License v3 (AGPL-3.0)
**Go**: 1.24.2+ (1.23.x acceptable as fallback if needed)
**Status**: Stable (v1.0.0)

## Installation

```bash
go get github.com/penguintechinc/project-template/shared/go_libs
```

## Features

### Validation (PyDAL-style)

Input validators following PyDAL's IS_* pattern with chainable API:

```go
package main

import (
    "fmt"
    "github.com/penguintechinc/project-template/shared/go_libs/validation"
)

func main() {
    // Single validator
    emailValidator := validation.Email()
    result := emailValidator.Validate("user@example.com")
    if !result.IsValid {
        fmt.Println("Error:", result.Error)
        return
    }

    // Chained validators
    validator := validation.Chain(
        validation.NotEmpty(),
        validation.Length(3, 255),
        validation.Email(),
    )

    result = validator.Validate("user@example.com")
    if result.IsValid {
        email := result.Value.(string)
        fmt.Println("Valid email:", email)
    }

    // Strong password validation
    passwordValidator := validation.StrongPassword(
        validation.WithPasswordMinLength(12),
        validation.WithPasswordRequireSpecial(true),
    )
    result = passwordValidator.Validate("SecureP@ss123!")
}
```

#### Available Validators

**String Validators:**
- `NotEmpty()` - Non-empty/non-whitespace strings
- `Length(min, max)` - Length constraints
- `MinLength(min)` - Minimum length
- `MaxLength(max)` - Maximum length
- `Match(pattern)` - Regex pattern matching
- `Alphanumeric()` - Alphanumeric only
- `Slug()` - URL-safe slugs
- `IsIn(options...)` - Membership in set

**Numeric Validators:**
- `IsInt()` - Integer type validation
- `IsFloat()` - Float type validation
- `IntInRange(min, max)` - Integer range
- `FloatInRange(min, max)` - Float range
- `IsPositive()` - Positive numbers
- `IsNegative()` - Negative numbers

**Network Validators:**
- `Email()` - Email format validation
- `URL()` - URL format validation
- `IPAddress()` - IPv4/IPv6 validation
- `Hostname()` - Hostname validation

**DateTime Validators:**
- `Date(format)` - Date format validation
- `DateTime(format)` - DateTime format validation
- `Time(format)` - Time format validation
- `DateInRange(start, end)` - Date range

**Password Validators:**
- `StrongPassword(opts...)` - Configurable password strength
- Functional options: `WithPasswordMinLength()`, `WithPasswordRequireSpecial()`, etc.

### Security

Security utilities for Gin applications:

```go
package main

import (
    "github.com/gin-gonic/gin"
    "github.com/penguintechinc/project-template/shared/go_libs/security"
)

func main() {
    router := gin.Default()

    // Add secure headers middleware
    router.Use(security.SecureHeaders())

    // Rate limiting middleware
    router.Use(security.RateLimit(100, 60)) // 100 requests per 60 seconds

    // CSRF protection
    router.Use(security.CSRFProtection())

    // Protected endpoint
    router.POST("/api/v1/data", func(c *gin.Context) {
        // Input sanitization
        rawInput := c.PostForm("data")
        safeInput := security.SanitizeInput(rawInput)

        c.JSON(200, gin.H{"processed": safeInput})
    })

    router.Run()
}
```

**Available Security Functions:**
- `SanitizeInput(input)` - XSS/HTML sanitization
- `EscapeSQL(input)` - SQL parameter escaping
- `SecureHeaders()` - Middleware for secure HTTP headers
- `RateLimit(maxRequests, windowSeconds)` - Rate limiting middleware
- `CSRFProtection()` - CSRF token validation middleware
- `AuditLog(action, details)` - Audit logging

### Cryptography

Modern cryptographic operations:

```go
package main

import (
    "fmt"
    "github.com/penguintechinc/project-template/shared/go_libs/crypto"
)

func main() {
    // Password hashing (bcrypt)
    password := "user_password"
    hash, err := crypto.HashPassword(password)
    if err != nil {
        panic(err)
    }

    // Password verification
    isValid, err := crypto.VerifyPassword(password, hash)
    if err != nil {
        panic(err)
    }
    fmt.Println("Password valid:", isValid) // true

    // Encryption (XChaCha20-Poly1305)
    key := []byte("32-byte-encryption-key-here----")
    plaintext := "Sensitive data"

    ciphertext, nonce, err := crypto.EncryptXChaCha20(plaintext, key)
    if err != nil {
        panic(err)
    }

    // Decryption
    decrypted, err := crypto.DecryptXChaCha20(ciphertext, nonce, key)
    if err != nil {
        panic(err)
    }
    fmt.Println("Decrypted:", decrypted)

    // Secure token generation
    token, err := crypto.GenerateToken(32)
    if err != nil {
        panic(err)
    }
    fmt.Println("Token:", token)
}
```

**Cryptographic Functions:**
- `HashPassword(password)` - bcrypt hashing
- `VerifyPassword(password, hash)` - Password verification
- `EncryptXChaCha20(plaintext, key)` - XChaCha20-Poly1305 encryption
- `DecryptXChaCha20(ciphertext, nonce, key)` - XChaCha20-Poly1305 decryption
- `EncryptAES(plaintext, key)` - AES-256-GCM encryption
- `DecryptAES(ciphertext, key)` - AES-256-GCM decryption
- `GenerateToken(length)` - Cryptographically secure random token
- `GenerateJWT(payload, secret)` - JWT creation
- `VerifyJWT(token, secret)` - JWT validation

### HTTP Client

Resilient HTTP client with correlation IDs and retries:

```go
package main

import (
    "fmt"
    "github.com/penguintechinc/project-template/shared/go_libs/http"
)

func main() {
    // Create HTTP client with retries
    client := http.NewClient(
        http.WithBaseURL("https://api.example.com"),
        http.WithTimeout(10),
        http.WithMaxRetries(3),
        http.WithBackoffFactor(0.5),
    )

    // Make request with automatic retries
    resp, err := client.Get("/users/123")
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    // With correlation ID
    clientWithCorr := http.NewClientWithCorrelation(
        "https://api.example.com",
    )
    resp, err = clientWithCorr.Post("/events",
        http.WithJSON(map[string]string{"type": "user_login"}),
    )
}
```

**HTTP Client Features:**
- Automatic retries with exponential backoff
- Correlation ID propagation for request tracking
- Connection pooling
- Timeout handling
- Stream responses
- Type-safe request building

### gRPC Integration

Production-ready gRPC server setup:

```go
package main

import (
    "fmt"
    "github.com/penguintechinc/project-template/shared/go_libs/grpc"
    "google.golang.org/grpc"
)

func main() {
    // Create gRPC server with TLS
    opts := []grpc.ServerOption{
        grpc.Creds(grpc.NewTLS(&tls.Config{
            Certificates: []tls.Certificate{cert},
        })),
    }

    server := grpc.NewServer(opts...)

    // Add interceptors
    server.RegisterService(&pb.YourService_ServiceDesc,
        grpc.NewAuthInterceptor("secret"),
    )

    fmt.Println("gRPC server listening on :50051")
    server.Serve(listener)
}
```

**gRPC Features:**
- TLS/SSL support
- Authentication interceptors
- Error handling
- Metadata propagation
- Streaming support

## Quick Start Examples

### Gin Application with Validation

```go
package main

import (
    "github.com/gin-gonic/gin"
    "github.com/penguintechinc/project-template/shared/go_libs/validation"
)

func main() {
    router := gin.Default()

    // Email validators
    emailValidator := validation.Chain(
        validation.NotEmpty(),
        validation.Length(3, 255),
        validation.Email(),
    )

    router.POST("/api/v1/users", func(c *gin.Context) {
        var req struct {
            Email string `json:"email"`
        }

        if err := c.BindJSON(&req); err != nil {
            c.JSON(400, gin.H{"error": err.Error()})
            return
        }

        // Validate email
        result := emailValidator.Validate(req.Email)
        if !result.IsValid {
            c.JSON(400, gin.H{"error": result.Error})
            return
        }

        // Use validated email
        email := result.Value.(string)
        c.JSON(201, gin.H{"email": email, "id": 123})
    })

    router.Run()
}
```

### Custom Validator

```go
package main

import (
    "fmt"
    "regexp"
    "github.com/penguintechinc/project-template/shared/go_libs/validation"
)

// IsPhoneNumber validates US phone numbers
func IsPhoneNumber() validation.Validator {
    return validation.ValidatorFunc(func(value any) validation.ValidationResult {
        s, ok := value.(string)
        if !ok {
            return validation.Failure("must be a string")
        }

        matched, _ := regexp.MatchString(`^\(\d{3}\)\s\d{3}-\d{4}$`, s)
        if !matched {
            return validation.Failure("invalid phone format")
        }

        return validation.Success(s)
    })
}

func main() {
    validator := IsPhoneNumber()
    result := validator.Validate("(555) 123-4567")
    fmt.Println("Valid:", result.IsValid)
}
```

### API Request Validation

```go
package main

import (
    "github.com/gin-gonic/gin"
    "github.com/penguintechinc/project-template/shared/go_libs/validation"
)

type UserRegistration struct {
    Email    string `json:"email"`
    Password string `json:"password"`
    Username string `json:"username"`
}

type ValidationErrors struct {
    Email    string `json:"email,omitempty"`
    Password string `json:"password,omitempty"`
    Username string `json:"username,omitempty"`
}

func ValidateRegistration(data *UserRegistration) *ValidationErrors {
    errors := &ValidationErrors{}

    // Validate email
    emailValidator := validation.Chain(
        validation.NotEmpty(),
        validation.Email(),
    )
    emailResult := emailValidator.Validate(data.Email)
    if !emailResult.IsValid {
        errors.Email = emailResult.Error
    }

    // Validate password
    passwordValidator := validation.StrongPassword()
    passwordResult := passwordValidator.Validate(data.Password)
    if !passwordResult.IsValid {
        errors.Password = passwordResult.Error
    }

    // Validate username
    usernameValidator := validation.Chain(
        validation.NotEmpty(),
        validation.Length(3, 30),
    )
    usernameResult := usernameValidator.Validate(data.Username)
    if !usernameResult.IsValid {
        errors.Username = usernameResult.Error
    }

    if errors.Email == "" && errors.Password == "" && errors.Username == "" {
        return nil
    }

    return errors
}

func main() {
    router := gin.Default()

    router.POST("/api/v1/register", func(c *gin.Context) {
        var req UserRegistration
        if err := c.BindJSON(&req); err != nil {
            c.JSON(400, gin.H{"error": "invalid request"})
            return
        }

        // Validate
        if errs := ValidateRegistration(&req); errs != nil {
            c.JSON(400, errs)
            return
        }

        c.JSON(201, gin.H{"message": "user created"})
    })

    router.Run()
}
```

## Configuration

### Environment Variables

```bash
# Security
GO_LIBS_SECURE_HEADERS=true
GO_LIBS_RATE_LIMIT_REDIS_URL=redis://localhost:6379

# Crypto
GO_LIBS_ENCRYPTION_KEY=your-32-byte-key-here

# gRPC
GO_LIBS_GRPC_CERT_FILE=/path/to/cert.pem
GO_LIBS_GRPC_KEY_FILE=/path/to/key.pem
```

## Development

### Setup

```bash
# Get dependencies
go mod download
go mod tidy

# Install development tools
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
```

### Running Tests

```bash
# Run all tests
go test ./...

# Run with coverage
go test -cover ./...
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out

# Run specific package tests
go test ./validation/...
```

### Code Quality

```bash
# Format code
go fmt ./...
goimports -w .

# Linting
golangci-lint run

# Security scanning
gosec ./...

# Run all checks
./scripts/lint.sh
```

### Build

```bash
# Build all packages
go build ./...

# Build with optimization
CGO_ENABLED=1 go build -ldflags="-s -w" ./...

# Cross-platform builds
GOOS=linux GOARCH=amd64 go build ./...
GOOS=darwin GOARCH=arm64 go build ./...
```

## Performance

### Optimization Tips

1. **Reuse Validators**: Create validators once and reuse them
   ```go
   emailValidator := validation.Email()  // Create once
   // Then use many times
   result1 := emailValidator.Validate("user1@example.com")
   result2 := emailValidator.Validate("user2@example.com")
   ```

2. **Use Connection Pooling**: Reuse HTTP clients
   ```go
   client := http.NewClient(
       http.WithBaseURL("https://api.example.com"),
   )
   // Use same client for multiple requests
   ```

3. **Streaming Responses**: For large responses
   ```go
   resp, _ := client.Get("/large-file")
   defer resp.Body.Close()
   // Stream from resp.Body
   ```

4. **Goroutines**: Leverage concurrency
   ```go
   results := make(chan Result, 10)
   for i := 0; i < 10; i++ {
       go func(id int) {
           result, _ := client.Get(fmt.Sprintf("/data/%d", id))
           results <- Result{ID: id, Data: result}
       }(i)
   }
   ```

## Common Issues

### Import errors with go.mod

**Solution**: Update go.mod with your module path:
```bash
go get -u github.com/penguintechinc/project-template/shared/go_libs
go mod tidy
```

### golangci-lint errors

**Solution**: Run lint fixer:
```bash
golangci-lint run --fix
```

### TLS certificate errors with gRPC

**Solution**: Generate proper certificates:
```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365
```

## License

GNU Affero General Public License v3 (AGPL-3.0)

This library is part of the Penguin Tech Inc project template. See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/penguintechinc/project-template/issues
- Documentation: https://docs.penguintech.io/go-libs
- Email: dev@penguintech.io

## See Also

- [Shared Libraries Overview](./overview.md)
- [Python Library](./py-libs.md)
- [Node.js Library](./node-libs.md)
