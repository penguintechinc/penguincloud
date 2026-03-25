# Team Management & Multi-Tenancy Guide

Comprehensive guide to creating, managing, and using teams in project-template.

## Table of Contents

1. [Overview](#overview)
2. [Team Concepts](#team-concepts)
3. [Creating Teams](#creating-teams)
4. [Managing Team Members](#managing-team-members)
5. [Team Roles and Permissions](#team-roles-and-permissions)
6. [Invitation Flow](#invitation-flow)
7. [Best Practices](#best-practices)
8. [API Reference](#api-reference)

---

## Overview

Teams enable multi-tenancy, allowing users to collaborate on shared resources. Each user automatically gets a personal team upon registration, and can create or join additional teams.

### Key Features

- **Personal Teams**: Each user has a personal team created automatically
- **Shared Teams**: Create teams with multiple members
- **Role-Based Access**: Control member permissions via team roles
- **Invitations**: Invite members via email with expiring tokens
- **Team Context**: API tokens include team information for team-scoped operations

---

## Team Concepts

### Users vs. Teams

```
User (individual account)
├── Personal Team (automatic, named "John's Team")
│   └── User as Owner
├── Development Team (created/joined)
│   ├── User as Admin
│   └── Other members...
└── Partners Team (joined via invitation)
    ├── User as Member
    └── Other members...
```

### Team Ownership and Admin

- **Owner**: Created team or designated by previous owner
  - Full access to all team resources
  - Can delete team
  - Can transfer ownership

- **Admin**: Designated by owner
  - Manage team members (invite, remove, change roles)
  - Manage team settings
  - Cannot delete team (owner only)

- **Member**: Standard team member
  - Access to team resources per role
  - Limited management capabilities

---

## Creating Teams

### Via API

```bash
curl -X POST https://api.example.com/api/v1/teams \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Development",
    "slug": "product-dev",
    "description": "Product team"
  }'
```

**Response**:
```json
{
  "id": "team_abc123",
  "name": "Product Development",
  "slug": "product-dev",
  "description": "Product team",
  "owner_id": "user_123",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Team Slug Rules

- Lowercase letters, numbers, and hyphens only
- Must start with letter
- 3-50 characters
- Must be unique within account
- Cannot change after creation

### Personal Teams

Personal teams are created automatically on user registration:

```
Email: user@example.com → Personal Team Slug: user-team
Name: "User's Team"
```

Users cannot delete personal teams.

---

## Managing Team Members

### List Members

```bash
curl https://api.example.com/api/v1/teams/{team_id}/members \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Add Member

**Requirements**: Team admin or owner

```bash
curl -X POST https://api.example.com/api/v1/teams/{team_id}/members \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_456",
    "role": "member"
  }'
```

### Update Member Role

**Requirements**: Team admin or owner

```bash
curl -X PUT https://api.example.com/api/v1/teams/{team_id}/members/{user_id} \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "admin"
  }'
```

### Remove Member

**Requirements**: Team admin or owner

```bash
curl -X DELETE https://api.example.com/api/v1/teams/{team_id}/members/{user_id} \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## Team Roles and Permissions

### Available Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **owner** | All team operations + delete team | Primary responsible for team |
| **admin** | Manage members + team settings | Trusted team leaders |
| **member** | Access team resources | Regular contributors |
| **viewer** | Read-only access | External stakeholders |

### Permission Matrix

| Action | Owner | Admin | Member | Viewer |
|--------|-------|-------|--------|--------|
| View team | ✓ | ✓ | ✓ | ✓ |
| Edit team | ✓ | ✓ | ✗ | ✗ |
| Delete team | ✓ | ✗ | ✗ | ✗ |
| Manage members | ✓ | ✓ | ✗ | ✗ |
| Create resources | ✓ | ✓ | ✓ | ✗ |
| Edit own resources | ✓ | ✓ | ✓ | ✗ |
| Delete resources | ✓ | ✓ | ✓ | ✗ |

---

## Invitation Flow

### Step 1: Send Invitation

Owner/Admin sends invitation:

```bash
curl -X POST https://api.example.com/api/v1/teams/{team_id}/invitations \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newmember@example.com",
    "role": "member"
  }'
```

**Response**:
```json
{
  "invitation_id": "inv_123",
  "email": "newmember@example.com",
  "role": "member",
  "status": "pending",
  "token": "inv_token_xyz...",
  "expires_at": "2024-01-22T10:30:00Z"
}
```

### Step 2: User Receives Email

Email sent to newmember@example.com containing:
- Team name
- Inviter name
- Acceptance link: `https://app.example.com/teams/join?token=inv_token_xyz...`
- Expiration time (7 days default)

### Step 3: Accept Invitation

**Option A: Registered User**

```bash
curl -X POST https://api.example.com/api/v1/teams/invitations/{token}/accept \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newmember@example.com"
  }'
```

**Option B: New User**

1. User clicks link in email
2. Redirected to registration: `https://app.example.com/register?invitation_token=...`
3. Register with email matching invitation
4. Automatically added to team

### Step 4: Confirmation

User added to team with assigned role:

```json
{
  "team_id": "team_abc123",
  "user_id": "user_789",
  "role": "member",
  "joined_at": "2024-01-15T11:00:00Z"
}
```

---

## Best Practices

### 1. Team Structure

- **Personal Team**: For user's individual work
- **Project Teams**: One team per major project/product
- **Cross-functional Teams**: For internal collaboration
- **Vendor/Partner Teams**: For external collaborations

### 2. Access Control

- **Principle of Least Privilege**: Assign minimum necessary role
- **Owner Separation**: Designate 2+ owners for critical teams
- **Audit Access**: Review team members periodically
- **Remove on Offboarding**: Immediately remove departing members

### 3. Invitation Management

- **Expiration**: Invitations expire after 7 days
- **Resend**: Admins can send new invitations if previous expired
- **Revoke**: Cancel pending invitations before acceptance
- **Batch Invite**: Consider bulk import for large teams

### 4. Role Assignment

```
User Hierarchy:
├── Global Admin (manages all users/teams)
├── Team Owner (primary responsible)
├── Team Admin (manages members, settings)
├── Team Member (uses resources)
└── Team Viewer (read-only access)
```

### 5. Resource Isolation

Resources created by team members are team-scoped:

```
Team 1 Resources:
├── Project A
├── Project B
└── Team Settings

Team 2 Resources (separate):
├── Project X
└── Team Settings

Personal Team:
└── Private resources
```

### 6. Security Considerations

- **Team Settings**: Restrict who can change team settings
- **Member Audit Logs**: Track all member changes
- **Deletion Protection**: Require owner confirmation for team deletion
- **Suspension**: Suspend teams instead of deleting for compliance

---

## API Reference

### Team Operations

- `POST /api/v1/teams` - Create team
- `GET /api/v1/teams` - List user's teams
- `GET /api/v1/teams/{team_id}` - Get team details
- `PUT /api/v1/teams/{team_id}` - Update team
- `DELETE /api/v1/teams/{team_id}` - Delete team (owner only)

### Member Management

- `GET /api/v1/teams/{team_id}/members` - List members
- `POST /api/v1/teams/{team_id}/members` - Add member (admin)
- `PUT /api/v1/teams/{team_id}/members/{user_id}` - Update role (admin)
- `DELETE /api/v1/teams/{team_id}/members/{user_id}` - Remove member (admin)

### Invitations

- `POST /api/v1/teams/{team_id}/invitations` - Send invitation
- `POST /api/v1/teams/invitations/{token}/accept` - Accept invitation
- `DELETE /api/v1/teams/{team_id}/invitations/{invite_id}` - Cancel invitation

📚 **See [API Documentation](API.md) for complete API reference with examples.**

---

## Examples

### Creating a Multi-Team Organization

```bash
#!/bin/bash
TOKEN="$1"

# 1. Create product team
PRODUCT=$(curl -s -X POST https://api.example.com/api/v1/teams \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Product", "slug": "product"}' \
  | jq -r '.id')

# 2. Create engineering team
ENGINEERING=$(curl -s -X POST https://api.example.com/api/v1/teams \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Engineering", "slug": "engineering"}' \
  | jq -r '.id')

# 3. Invite members
curl -s -X POST https://api.example.com/api/v1/teams/$PRODUCT/invitations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "role": "admin"}' > /dev/null

# 4. Output team IDs
echo "Product Team: $PRODUCT"
echo "Engineering Team: $ENGINEERING"
```

### Team Switching in UI

When user has multiple teams, app should allow switching:

```javascript
// JavaScript example
const userTeams = JWT.decode(token).team_ids;
const currentTeam = JWT.decode(token).current_team_id;

// UI shows: "You are in: ProductTeam [Switch]"
// Clicking switch updates current_team_id in new token
```

---

**Last Updated**: 2024-01-15
**Version**: 1.0.0
