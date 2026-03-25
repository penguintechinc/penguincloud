# Integration Patterns - Code Examples

Production-ready code examples for common integration patterns in the Project Template.

## Overview

The template supports multiple integration patterns:

- **Flask + Flask-Security-Too + Hybrid Database**: Authentication and database setup
- **Hybrid Database Architecture**: SQLAlchemy for init, PyDAL for operations
- **ReactJS Frontend Integration**: Secure API communication
- **License-Gated Features**: Enterprise feature licensing
- **Monitoring Integration**: Prometheus metrics and observability

## Configuration

Required environment variables:

```bash
# Database Configuration
DB_TYPE=postgres                          # postgres, mysql, or sqlite
DB_HOST=localhost
DB_PORT=5432
DB_USER=app_user
DB_PASS=secure_password
DB_NAME=app_database
DB_POOL_SIZE=10

# Flask Configuration
SECRET_KEY=your-secret-key-here
SECURITY_PASSWORD_SALT=your-security-salt

# Galera Cluster (optional)
GALERA_MODE=false

# License Server (optional)
LICENSE_KEY=PENG-XXXX-XXXX-XXXX-XXXX-ABCD
LICENSE_SERVER_URL=https://license.penguintech.io

# Frontend
REACT_APP_API_URL=http://localhost:5000
```

---

## 1. Flask + Flask-Security-Too + Hybrid Database

Complete authentication setup with hybrid database approach.

### Key Features

- User authentication and RBAC
- Password hashing with bcrypt
- Protected endpoints with JWT
- Health check endpoint

### Implementation

```python
from flask import Flask, jsonify
from flask_security import Security, auth_required, current_user
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, Text
from pydal import DAL, Field
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'dev-salt')

DB_TYPE = os.getenv('DB_TYPE', 'postgres')
DB_URLS = {
    'postgres': f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
    'mysql': f"mysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
    'sqlite': f"sqlite:///{os.getenv('DB_PATH', 'app.db')}"
}

def init_database():
    """Use SQLAlchemy for initial schema creation"""
    engine = create_engine(DB_URLS[DB_TYPE])
    metadata = MetaData()

    Table('users', metadata,
        Column('id', Integer, primary_key=True),
        Column('email', String(255), unique=True, nullable=False),
        Column('password', String(255)),
        Column('active', Boolean, default=True),
        Column('fs_uniquifier', String(255), unique=True))

    Table('roles', metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String(80), unique=True),
        Column('description', Text))

    metadata.create_all(engine)
    engine.dispose()

# PyDAL for day-to-day operations
db = DAL(DB_URLS[DB_TYPE], pool_size=10, migrate=True)

db.define_table('users',
    Field('email', 'string', unique=True),
    Field('password', 'string'),
    Field('active', 'boolean', default=True),
    Field('fs_uniquifier', 'string', unique=True))

db.define_table('roles',
    Field('name', 'string', unique=True),
    Field('description', 'text'))

from flask_security import PyDALUserDatastore
user_datastore = PyDALUserDatastore(db, db.users, db.roles)
security = Security(app, user_datastore)

@app.route('/healthz', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'flask-backend'}), 200

@app.route('/api/v1/protected', methods=['GET'])
@auth_required()
def protected_resource():
    return jsonify({
        'message': 'This is a protected endpoint',
        'user': current_user.email
    }), 200
```

---

## 2. Hybrid Database Architecture

Advanced database configuration with Galera cluster support.

### Key Features

- Multi-database support (PostgreSQL, MySQL, SQLite)
- Memory-efficient dataclasses with slots
- Galera cluster retry logic
- Thread-safe connection pooling

### Implementation

```python
from pydal import DAL, Field
from dataclasses import dataclass
import os
import time
from functools import wraps
import logging

logger = logging.getLogger(__name__)

VALID_DB_TYPES = {'postgres', 'mysql', 'sqlite'}

@dataclass(slots=True, frozen=True)
class UserModel:
    """User model with slots for memory efficiency"""
    id: int
    email: str
    name: str
    active: bool

def get_db_url() -> str:
    """Build database URL based on DB_TYPE"""
    db_type = os.getenv('DB_TYPE', 'postgres')

    if db_type not in VALID_DB_TYPES:
        raise ValueError(f"Invalid DB_TYPE: {db_type}")

    if db_type == 'sqlite':
        return f"sqlite:///{os.getenv('DB_PATH', 'app.db')}"

    return (f"{'postgresql' if db_type == 'postgres' else 'mysql'}://"
            f"{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@"
            f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/"
            f"{os.getenv('DB_NAME')}")

def get_db_connection() -> DAL:
    """Initialize PyDAL for day-to-day operations"""
    db_type = os.getenv('DB_TYPE', 'postgres')
    galera_mode = os.getenv('GALERA_MODE', 'false').lower() == 'true'

    dal_kwargs = {
        'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
        'migrate_enabled': True,
        'check_reserved': ['all'],
        'lazy_tables': True
    }

    if galera_mode and db_type == 'mysql':
        dal_kwargs['driver_args'] = {
            'init_command': (
                'SET wsrep_sync_wait=1; '
                'SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;'
            )
        }

    return DAL(get_db_url(), **dal_kwargs)

def galera_retry(max_retries=3, delay=0.5):
    """Retry decorator for Galera WSREP_NOT_READY errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if 'WSREP' in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Galera WSREP error, retrying")
                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
        return wrapper
    return decorator

db = get_db_connection()

db.define_table('users',
    Field('email', 'string', unique=True, notnull=True),
    Field('name', 'string'),
    Field('active', 'boolean', default=True))

@galera_retry(max_retries=3)
def create_user(email: str, name: str) -> int:
    """Create user with Galera retry logic"""
    return db.users.insert(email=email, name=name, active=True)

@galera_retry(max_retries=3)
def get_user(user_id: int) -> UserModel:
    """Retrieve user with Galera retry logic"""
    user = db.users[user_id]
    if not user:
        raise ValueError(f"User {user_id} not found")
    return UserModel(id=user.id, email=user.email, name=user.name, active=user.active)
```

---

## 3. ReactJS Frontend Integration

Secure API communication from React frontend.

### Key Features

- Axios HTTP client with base configuration
- JWT token authentication
- Request/response interceptors
- Protected components with loading states

### Implementation

```javascript
// api/client.js
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// components/ProtectedComponent.jsx
import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

function ProtectedComponent() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await apiClient.get('/api/v1/protected');
        setData(response.data);
        setError(null);
      } catch (err) {
        setError(err.message || 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h2>Protected Resource</h2>
      <p>{data?.message}</p>
      <p>User: {data?.user}</p>
    </div>
  );
}

export default ProtectedComponent;
```

---

## 4. License-Gated Features

Enterprise feature licensing with Flask-Security-Too.

### Key Features

- Decorator-based feature gating
- License key validation
- Development vs production mode
- Graceful fallback for unlicensed features

### Implementation

```python
from functools import wraps
from flask import jsonify
from flask_security import auth_required, current_user
import os
import logging

logger = logging.getLogger(__name__)

class LicenseValidator:
    """Handle license validation and feature gating"""

    def __init__(self):
        self.license_key = os.getenv('LICENSE_KEY')
        self.release_mode = os.getenv('RELEASE_MODE', 'false').lower() == 'true'

    def is_feature_available(self, feature_name: str) -> bool:
        """Check if feature is available"""
        if not self.release_mode:
            logger.info(f"Development mode: feature '{feature_name}' available")
            return True
        # Implement license server validation in production
        return True

license_validator = LicenseValidator()

def requires_feature(feature_name: str):
    """Decorator to gate features behind license checks"""
    def decorator(f):
        @wraps(f)
        @auth_required()
        def decorated_function(*args, **kwargs):
            if not license_validator.is_feature_available(feature_name):
                return jsonify({
                    'error': 'Feature not available with current license',
                    'feature': feature_name,
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/api/v1/advanced/analytics', methods=['GET'])
@requires_feature("advanced_analytics")
def generate_advanced_report():
    """Advanced analytics requires professional+ license"""
    return jsonify({
        'report': 'Advanced Analytics Report',
        'user': current_user.email
    }), 200
```

---

## 5. Monitoring Integration

Prometheus metrics integration for observability.

### Key Features

- Request counter and duration histogram
- Prometheus metrics endpoint
- Per-endpoint tracking
- Grafana dashboard integration

### Implementation

```python
from prometheus_client import Counter, Histogram, generate_latest, CollectorRegistry
from flask import Response
import time
import functools

registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    registry=registry
)

def track_metrics(f):
    """Decorator to track request metrics"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        try:
            result = f(*args, **kwargs)
            status = result[1] if isinstance(result, tuple) else 200
            return result
        except Exception:
            status = 500
            raise
        finally:
            duration = time.time() - start_time
            endpoint = f.__name__
            REQUEST_DURATION.labels(method='GET', endpoint=endpoint).observe(duration)
            REQUEST_COUNT.labels(method='GET', endpoint=endpoint, status=status).inc()
    return decorated_function

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(registry), mimetype='text/plain')

@app.route('/api/v1/protected', methods=['GET'])
@auth_required()
@track_metrics
def protected_resource():
    """Protected endpoint with metric tracking"""
    return jsonify({'message': 'Protected endpoint'}), 200
```

---

## Best Practices

### Security

1. Always use Flask-Security-Too for authentication
2. Validate all user input using shared libraries (py_libs, go_libs, node_libs)
3. Use environment variables for secrets
4. Implement rate limiting
5. Enable CORS carefully - restrict to known origins

### Performance

1. Use connection pooling (10-20 for most applications)
2. Implement caching for frequently accessed data
3. Use async/await for I/O-bound operations
4. Monitor query performance
5. Use dataclasses with slots for memory-efficient models

### Error Handling

1. Log all errors with context
2. Implement retry logic for transient failures
3. Return meaningful error messages
4. Handle database connection failures gracefully

### Database Management

1. Always use explicit primary keys (Galera requirement)
2. Use PyDAL for migrations
3. Test with all supported database types
4. Implement connection retry logic
5. Monitor connection pool

---

## Related Documentation

- [Flask-Security-Too](https://flask-security-too.readthedocs.io/)
- [PyDAL](https://py4web.io/_documentation/static/en/chapter-09.html)
- [SQLAlchemy](https://docs.sqlalchemy.org/)
- [React](https://react.dev/)
- [Prometheus](https://prometheus.io/docs/)
- [Development Standards](../STANDARDS.md)
- [License Server Integration](../licensing/license-server-integration.md)

---

**Last Updated**: 2025-12-19
**Template Version**: 1.5.0
**Maintained by**: Penguin Tech Inc
