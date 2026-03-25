# API Documentation

Complete API reference for project-template services.

## Table of Contents

1. [Authentication APIs](#authentication-apis)
2. [Team Management APIs](#team-management-apis)
3. [User Management APIs](#user-management-apis)
4. [License APIs](#license-apis)
5. [Health & Status APIs](#health--status-apis)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)

---

## Authentication APIs

### Login

**Request**:
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "123",
    "email": "user@example.com",
    "name": "John Doe",
    "role": "maintainer",
    "team_ids": ["team_1"]
  }
}
```

### Register

**Request**:
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "newuser@example.com",
  "password": "securepassword",
  "name": "Jane Doe"
}
```

**Response** (201 Created):
```json
{
  "user": {
    "id": "456",
    "email": "newuser@example.com",
    "name": "Jane Doe",
    "role": "viewer",
    "team_ids": ["personal_team_456"]
  }
}
```

### Refresh Token

**Request**:
```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Logout

**Request**:
```http
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "message": "Logged out successfully"
}
```

### Current User

**Request**:
```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "id": "123",
  "email": "user@example.com",
  "name": "John Doe",
  "role": "maintainer",
  "team_ids": ["team_1", "team_2"],
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Team Management APIs

### Create Team

**Request**:
```http
POST /api/v1/teams
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "My Organization",
  "slug": "my-org",
  "description": "Team description (optional)"
}
```

**Response** (201 Created):
```json
{
  "id": "team_abc123",
  "name": "My Organization",
  "slug": "my-org",
  "description": "Team description",
  "owner_id": "user_123",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### List User's Teams

**Request**:
```http
GET /api/v1/teams
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "teams": [
    {
      "id": "team_abc123",
      "name": "My Organization",
      "slug": "my-org",
      "role": "owner"
    },
    {
      "id": "team_xyz789",
      "name": "Partner Org",
      "slug": "partner-org",
      "role": "member"
    }
  ],
  "count": 2
}
```

### Get Team Details

**Request**:
```http
GET /api/v1/teams/{team_id}
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "id": "team_abc123",
  "name": "My Organization",
  "slug": "my-org",
  "description": "Team description",
  "owner_id": "user_123",
  "is_active": true,
  "member_count": 5,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Update Team

**Request**:
```http
PUT /api/v1/teams/{team_id}
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response** (200 OK):
```json
{
  "id": "team_abc123",
  "name": "Updated Name",
  "description": "Updated description",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

### Delete Team

**Request**:
```http
DELETE /api/v1/teams/{team_id}
Authorization: Bearer <access_token>
```

**Response** (204 No Content)

### List Team Members

**Request**:
```http
GET /api/v1/teams/{team_id}/members
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "members": [
    {
      "user_id": "user_123",
      "name": "John Doe",
      "email": "john@example.com",
      "role": "owner",
      "joined_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 1
}
```

### Invite Team Member

**Request**:
```http
POST /api/v1/teams/{team_id}/invitations
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email": "newmember@example.com",
  "role": "member"
}
```

**Response** (201 Created):
```json
{
  "invitation_id": "inv_123",
  "email": "newmember@example.com",
  "role": "member",
  "status": "pending",
  "expires_at": "2024-01-22T10:30:00Z"
}
```

### Accept Invitation

**Request**:
```http
POST /api/v1/teams/invitations/{token}/accept
Content-Type: application/json

{
  "email": "newmember@example.com"
}
```

**Response** (200 OK):
```json
{
  "team_id": "team_abc123",
  "message": "Invitation accepted successfully"
}
```

---

## User Management APIs

### List Users (Admin Only)

**Request**:
```http
GET /api/v1/users
Authorization: Bearer <access_token>
```

**Query Parameters**:
- `page` (optional, default: 1)
- `limit` (optional, default: 20, max: 100)
- `search` (optional, filter by email/name)

**Response** (200 OK):
```json
{
  "users": [
    {
      "id": "user_123",
      "email": "user@example.com",
      "name": "John Doe",
      "role": "maintainer",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 45
  }
}
```

### Get User (Admin Only)

**Request**:
```http
GET /api/v1/users/{user_id}
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "John Doe",
  "role": "maintainer",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Update User Profile (Self)

**Request**:
```http
PUT /api/v1/users/me
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Jane Doe",
  "email": "janedoe@example.com"
}
```

**Response** (200 OK):
```json
{
  "id": "user_123",
  "name": "Jane Doe",
  "email": "janedoe@example.com",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

### Change Password

**Request**:
```http
PUT /api/v1/users/me/password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "oldpassword",
  "new_password": "newpassword"
}
```

**Response** (200 OK):
```json
{
  "message": "Password changed successfully"
}
```

---

## License APIs

### Get License Status (Admin Only)

**Request**:
```http
GET /api/v1/license/status
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "valid": true,
  "tier": "professional",
  "features": ["teams", "sso", "audit_logs"],
  "expires_at": "2025-01-15T00:00:00Z",
  "limits": {
    "team_count": 50,
    "user_count": 500,
    "storage_gb": 100
  }
}
```

---

## Health & Status APIs

### Health Check

**Request**:
```http
GET /healthz
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "v1.0.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Readiness Check

**Request**:
```http
GET /readyz
```

**Response** (200 OK):
```json
{
  "ready": true,
  "database": "ok",
  "cache": "ok"
}
```

### Metrics (Prometheus)

**Request**:
```http
GET /metrics
```

**Response** (200 OK):
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/v1/auth/login",status="200"} 42
```

---

## Error Handling

All errors follow standard HTTP status codes with JSON response:

```json
{
  "error": "Error code",
  "message": "Human-readable error message",
  "details": {}
}
```

**Common Error Codes**:

| Status | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Invalid request parameters |
| 401 | `unauthorized` | Missing or invalid authentication |
| 403 | `forbidden` | Insufficient permissions |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | Resource already exists |
| 429 | `rate_limited` | Rate limit exceeded |
| 500 | `server_error` | Internal server error |

**Example Error Response**:
```json
{
  "error": "unauthorized",
  "message": "Invalid or expired token",
  "details": {
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

---

## Rate Limiting

### Default Limits

| Endpoint | Limit |
|----------|-------|
| `/api/v1/auth/login` | 10 requests/minute per IP |
| `/api/v1/auth/register` | 10 requests/hour per IP |
| General API endpoints | 100 requests/minute per user |

### Rate Limit Headers

All responses include rate limit information:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705329600
```

When limit exceeded (429 response):

```
Retry-After: 60
X-RateLimit-Reset: 1705329600
```

---

**Last Updated**: 2024-01-15
**API Version**: v1
