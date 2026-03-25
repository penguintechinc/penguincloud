# Application-Specific Standards

**This file contains context specific to this application.** It should be customized for each project forked from the template. The generic `CLAUDE.md` file is kept template-wide and can be updated across all projects without losing app-specific information.

## Project Context

### Application Name
[Add your application name here]

### Project Description
[Add a 1-2 paragraph description of what this application does]

### Key Business Requirements
- [Add critical business requirements]
- [Add domain-specific features]
- [Add compliance or regulatory requirements]

## Architecture Overview

### Core Services
[Document the specific containers/services used in this application]

**Example:**
- **flask-backend**: User management, order processing, API
- **go-backend**: Real-time notifications, high-performance data processing
- **webui**: Admin dashboard, customer portal
- **connector**: Third-party integrations (payment processing, shipping, etc.)

### Technology Choices
[Document specific tech stack decisions and rationale]

**Example:**
- **Database**: PostgreSQL (multi-tenant support required)
- **Cache**: Redis (session storage, real-time data)
- **Message Queue**: RabbitMQ (async order processing)
- **Search**: Elasticsearch (full-text search for products)

### Data Model Overview
[Brief overview of core entities and relationships]

### Integration Points
[Document external systems and integrations]

**Example:**
- Stripe for payment processing
- SendGrid for email notifications
- AWS S3 for file storage
- Twilio for SMS notifications

## Application-Specific Requirements

### Feature Requirements
[Document critical features specific to this application]

### Performance Requirements
[Document specific performance SLAs]

**Example:**
- API response time: <100ms p95
- Search indexing: Near real-time (<1s latency)
- Concurrent users supported: 10,000+
- Database transactions: 500+ TPS

### Scalability Requirements
[Document expected growth and scaling needs]

### Security & Compliance
[Document app-specific security requirements]

**Example:**
- PCI DSS compliance (payment handling)
- GDPR compliance (user data)
- SOC2 Type II certification needed
- Data encryption at rest and in transit

## Domain-Specific Standards

### Business Logic Patterns
[Document patterns specific to your domain]

### API Endpoints Overview
[High-level grouping of API endpoints by domain]

**Example:**
```
/api/v1/auth/*        - Authentication endpoints
/api/v1/users/*       - User management
/api/v1/products/*    - Product catalog
/api/v1/orders/*      - Order management
/api/v1/payments/*    - Payment processing
/api/v1/reports/*     - Analytics and reporting
```

### Database Schema Overview
[Link to or document key tables and their relationships]

### Custom Roles & Permissions
[Document application-specific roles beyond the standard Admin/Maintainer/Viewer]

**Example:**
- **Product Manager**: Can manage products, pricing, but not process refunds
- **Support Agent**: Can view orders and respond to tickets, but not process payments
- **Finance Admin**: Can view financial reports but not access customer data
- **Warehouse Manager**: Can manage inventory but not access pricing

## Development Setup

### Prerequisites
[App-specific setup beyond template requirements]

**Example:**
- Stripe test API keys configured
- SendGrid account and API key
- AWS S3 bucket created
- Elasticsearch cluster running

### Local Development Environment
[Any additional setup or configuration beyond docs/DEVELOPMENT.md]

### Mock Data
[App-specific mock data seeding beyond standard template patterns]

**Example:**
- 5-10 sample products with variants
- 3-5 test users with different roles
- Sample orders in various states (pending, shipped, delivered, refunded)

## Testing Standards

### Critical User Flows to Test
[App-specific workflows that must be tested]

**Example:**
- User registration and email confirmation
- Product search and filter
- Add to cart, checkout, payment processing
- Order tracking and delivery status

### Performance Test Scenarios
[Specific load testing requirements]

**Example:**
- 1,000 concurrent product searches
- 100 concurrent order placements
- Search indexing of 100,000 products

## Deployment & Operations

### Environment-Specific Configuration
[App-specific environment variables and settings]

### Monitoring & Alerting
[App-specific metrics and alerts]

**Example:**
- Alert if payment processing fails (critical)
- Alert if search index is stale >5 minutes
- Track order fulfillment time distribution

### Backup & Recovery
[App-specific backup strategy]

**Example:**
- Daily database backups to S3
- Transaction logs for point-in-time recovery
- 30-day retention policy

## Known Limitations & Constraints

[Document any known issues, limitations, or architectural constraints specific to this application]

**Example:**
- Single payment gateway (Stripe only) - no multi-gateway support
- Customer data limited to 10MB per user
- Search index refreshes every 1 minute (near real-time)

## Common Tasks & Runbooks

### [Task Name]
[Step-by-step instructions for common operational tasks]

**Example:** Handling Refunds
1. Customer initiates refund through dashboard
2. Support team verifies order in admin panel
3. Click "Process Refund" button
4. Stripe processes refund (5-10 business days)
5. Customer receives notification

## Future Roadmap

[Document planned features or architectural changes]

---

**Last Updated**: [Date]
**Maintained By**: [Team/Person]
**Related Documentation**: CLAUDE.md, docs/STANDARDS.md, docs/DEVELOPMENT.md, docs/TESTING.md
