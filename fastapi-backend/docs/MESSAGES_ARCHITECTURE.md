# Breeder Messages System - Architecture Documentation

## System Overview

The Breeder Messages system is a full-stack feature that enables anonymous users to contact breeders and allows breeders to manage their inquiries through a centralized inbox.

### Technology Stack

**Backend:**
- Framework: FastAPI (Python 3.9+)
- Database: PostgreSQL 13+
- ORM: SQLAlchemy (async)
- Validation: Pydantic v2
- Authentication: JWT tokens

**Frontend:**
- Framework: Angular 21
- Language: TypeScript 5+
- HTTP Client: Angular HttpClient
- Forms: Reactive Forms
- Styling: Custom CSS with Tailwind utilities


## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Angular)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ ContactBreeder   │  │ NotificationIcon │  │  MessagesList   │  │
│  │   Component      │  │    Component     │  │   Component     │  │
│  │                  │  │                  │  │                 │  │
│  │ - Contact Form   │  │ - Unread Badge   │  │ - Filter Tabs   │  │
│  │ - Validation     │  │ - Auto-polling   │  │ - Pagination    │  │
│  │ - Submit         │  │ - Navigation     │  │ - Sorting       │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘  │
│           │                     │                     │            │
│           └─────────────────────┼─────────────────────┘            │
│                                 │                                  │
│                    ┌────────────▼────────────┐                     │
│                    │   MessageService        │                     │
│                    │                         │                     │
│                    │ - sendMessage()         │                     │
│                    │ - getMessages()         │                     │
│                    │ - getUnreadCount()      │                     │
│                    │ - getMessage()          │                     │
│                    │ - markAsRead()          │                     │
│                    │ - respondToMessage()    │                     │
│                    └────────────┬────────────┘                     │
│                                 │                                  │
└─────────────────────────────────┼──────────────────────────────────┘
                                  │
                                  │ HTTP/JSON
                                  │ JWT Auth
                                  │
┌─────────────────────────────────▼──────────────────────────────────┐
│                         BACKEND (FastAPI)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                    ┌────────────────────────┐                      │
│                    │   Messages Router      │                      │
│                    │  /api/messages/*       │                      │
│                    │                        │                      │
│                    │ POST   /send           │ (public)             │
│                    │ GET    /               │ (protected)          │
│                    │ GET    /unread-count   │ (protected)          │
│                    │ GET    /{id}           │ (protected)          │
│                    │ PATCH  /{id}/read      │ (protected)          │
│                    │ POST   /{id}/respond   │ (protected)          │
│                    └────────────┬───────────┘                      │
│                                 │                                  │
│                    ┌────────────▼───────────┐                      │
│                    │   Message Schemas      │                      │
│                    │   (Pydantic)           │                      │
│                    │                        │                      │
│                    │ - MessageCreate        │                      │
│                    │ - MessageResponse      │                      │
│                    │ - MessageListItem      │                      │
│                    │ - MessageListResponse  │                      │
│                    │ - MessageUpdate        │                      │
│                    │ - MessageResponseCreate│                      │
│                    └────────────┬───────────┘                      │
│                                 │                                  │
│                    ┌────────────▼───────────┐                      │
│                    │   Message Model        │                      │
│                    │   (SQLAlchemy)         │                      │
│                    │                        │                      │
│                    │ - id (UUID)            │                      │
│                    │ - breeder_id (FK)      │                      │
│                    │ - sender_name          │                      │
│                    │ - sender_email         │                      │
│                    │ - message              │                      │
│                    │ - is_read              │                      │
│                    │ - response_text        │                      │
│                    │ - responded_at         │                      │
│                    │ - created_at           │                      │
│                    │ - updated_at           │                      │
│                    └────────────┬───────────┘                      │
│                                 │                                  │
└─────────────────────────────────┼──────────────────────────────────┘
                                  │
                                  │ SQL
                                  │
┌─────────────────────────────────▼──────────────────────────────────┐
│                      DATABASE (PostgreSQL)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      messages table                          │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │ id               UUID PRIMARY KEY                            │  │
│  │ breeder_id       UUID REFERENCES users(id) ON DELETE CASCADE │  │
│  │ sender_name      VARCHAR(255) NOT NULL                       │  │
│  │ sender_email     VARCHAR(255) NOT NULL                       │  │
│  │ message          TEXT                                        │  │
│  │ is_read          BOOLEAN DEFAULT FALSE                       │  │
│  │ response_text    TEXT                                        │  │
│  │ responded_at     TIMESTAMP                                   │  │
│  │ created_at       TIMESTAMP DEFAULT NOW()                     │  │
│  │ updated_at       TIMESTAMP DEFAULT NOW()                     │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │ Indexes:                                                     │  │
│  │ - idx_messages_breeder_id (breeder_id)                       │  │
│  │ - idx_messages_is_read (is_read)                             │  │
│  │ - idx_messages_sender_email (sender_email)                   │  │
│  │ - idx_messages_created_at (created_at)                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```


## Data Flow

### 1. Anonymous User Sends Message

```
User Action → Contact Form → MessageService.sendMessage()
    ↓
POST /api/messages/send
    ↓
Validate breeder_id exists
    ↓
Create Message record
    ↓
Save to database
    ↓
Return success response
    ↓
Show success toast
```

### 2. Breeder Views Messages

```
Page Load → MessagesListComponent.ngOnInit()
    ↓
MessageService.getMessages(filters)
    ↓
GET /api/messages/?status=all&limit=20&offset=0&sort=newest
    ↓
Query messages WHERE breeder_id = current_user.id
    ↓
Apply filters (read/unread)
    ↓
Apply sorting (newest/oldest)
    ↓
Apply pagination (limit/offset)
    ↓
Return MessageListResponse
    ↓
Render messages in UI
```

### 3. Notification Badge Updates

```
NotificationIconComponent.ngOnInit()
    ↓
Start polling interval (30 seconds)
    ↓
MessageService.getUnreadCount()
    ↓
GET /api/messages/unread-count
    ↓
Query COUNT(*) WHERE breeder_id = user.id AND is_read = false
    ↓
Return UnreadCountResponse
    ↓
Update badge display
    ↓
Wait 30 seconds → Repeat
```

### 4. Breeder Reads Message

```
User clicks message → Navigate to /settings/messages/:id
    ↓
MessageDetailComponent.ngOnInit()
    ↓
MessageService.getMessage(id)
    ↓
GET /api/messages/{id}
    ↓
Query message WHERE id = :id AND breeder_id = current_user.id
    ↓
Return MessageResponse
    ↓
Display message details
    ↓
Auto-trigger markAsRead()
    ↓
PATCH /api/messages/{id}/read
    ↓
UPDATE messages SET is_read = true WHERE id = :id
    ↓
Update UI status badge
```

### 5. Breeder Responds to Message

```
User types response → Clicks "Send Response"
    ↓
MessageService.respondToMessage(id, response_text)
    ↓
POST /api/messages/{id}/respond
    ↓
Validate response_text (1-5000 chars)
    ↓
UPDATE messages SET 
  response_text = :text,
  responded_at = NOW(),
  is_read = true
WHERE id = :id AND breeder_id = current_user.id
    ↓
Return updated MessageResponse
    ↓
Display response in UI
    ↓
Update status badge to "Responded"
```


## Component Details

### Frontend Components

#### 1. ContactBreederComponent

**Purpose**: Modal dialog for anonymous users to send messages to breeders

**Inputs:**
- `breederId: string` - UUID of the breeder
- `breederName: string` - Display name

**Features:**
- Reactive form with validation
- Email format validation
- Character counter (2000 char limit)
- Loading state during submission
- Success/error toast notifications

**Files:**
- `contact-breeder.component.ts`
- `contact-breeder.component.html`
- `contact-breeder.component.css`

#### 2. NotificationIconComponent

**Purpose**: Display unread message count in header

**Features:**
- Auto-polling every 30 seconds
- Badge display (1-99, 99+)
- Navigation to messages page
- Responsive design

**Files:**
- `notification-icon.component.ts`
- `notification-icon.component.html`
- `notification-icon.component.css`

#### 3. MessagesListComponent

**Purpose**: Display paginated list of messages with filtering

**Features:**
- Filter tabs (All/Unread/Read)
- Sort dropdown (Newest/Oldest)
- Pagination (20 per page)
- Message preview cards
- Status badges (New/Read/Responded)
- Relative timestamps
- Empty state
- Loading state
- Refresh button

**Files:**
- `messages-list.component.ts`
- `messages-list.component.html`
- `messages-list.component.css`

#### 4. MessageDetailComponent

**Purpose**: Display full message and response form

**Features:**
- Full message display
- Sender information
- Auto-mark as read
- Response form (5000 char limit)
- Character counter
- Edit response capability
- Back navigation
- Loading states

**Files:**
- `message-detail.component.ts`
- `message-detail.component.html`
- `message-detail.component.css`

### Backend Components

#### 1. Message Model (SQLAlchemy)

**File**: `app/models/message.py`

**Fields:**
- `id`: UUID primary key
- `breeder_id`: Foreign key to users table
- `sender_name`: VARCHAR(255)
- `sender_email`: VARCHAR(255)
- `message`: TEXT (nullable)
- `is_read`: BOOLEAN (default: false)
- `response_text`: TEXT (nullable)
- `responded_at`: TIMESTAMP (nullable)
- `created_at`: TIMESTAMP (auto)
- `updated_at`: TIMESTAMP (auto)

**Relationships:**
- `breeder`: Many-to-one with User model

#### 2. Message Schemas (Pydantic)

**File**: `app/schemas/message.py`

**Schemas:**
- `MessageCreate`: For sending messages (public)
- `MessageResponse`: Full message details
- `MessageListItem`: List view with preview
- `MessageListResponse`: Paginated list response
- `MessageUpdate`: For marking as read
- `MessageResponseCreate`: For breeder responses
- `UnreadCountResponse`: Unread count
- `MessageSendResponse`: Send confirmation

#### 3. Messages Router (FastAPI)

**File**: `app/routers/messages.py`

**Endpoints:**

1. `POST /api/messages/send` (public)
   - Send message to breeder
   - No authentication required
   - Validates breeder exists

2. `GET /api/messages/` (protected)
   - List messages for authenticated breeder
   - Supports filtering, sorting, pagination
   - Returns total count and unread count

3. `GET /api/messages/unread-count` (protected)
   - Get unread message count
   - Used for notification badge

4. `GET /api/messages/{id}` (protected)
   - Get single message details
   - Verifies message belongs to breeder

5. `PATCH /api/messages/{id}/read` (protected)
   - Mark message as read
   - Idempotent operation

6. `POST /api/messages/{id}/respond` (protected)
   - Add response to message
   - Auto-marks as read
   - Records response timestamp


## Security Architecture

### Authentication & Authorization

**Public Endpoints:**
- `POST /api/messages/send` - No authentication required
  - Allows anonymous users to contact breeders
  - Validates breeder_id exists before creating message

**Protected Endpoints:**
- All other endpoints require JWT authentication
- Token must be present in Authorization header: `Bearer <token>`
- User must be authenticated and active

**Authorization Rules:**
- Breeders can only access their own messages
- All queries filtered by `breeder_id = current_user.id`
- Prevents cross-breeder message access

### Data Validation

**Backend (Pydantic):**
- Email format validation
- String length limits (name: 255, message: 2000, response: 5000)
- Required field validation
- UUID format validation
- Automatic data sanitization

**Frontend (Angular):**
- Reactive form validators
- Email format validation
- Character count validation
- Required field validation
- Real-time validation feedback

### SQL Injection Prevention

- SQLAlchemy ORM used for all database queries
- Parameterized queries prevent SQL injection
- No raw SQL strings with user input

### XSS Prevention

**Backend:**
- Pydantic automatically escapes special characters
- No HTML rendering on backend

**Frontend:**
- Angular's built-in XSS protection
- Template sanitization
- No `innerHTML` usage with user data

### CSRF Protection

- JWT tokens used instead of cookies
- No CSRF vulnerability with token-based auth
- Tokens stored in localStorage (not cookies)


## Performance Optimization

### Database Optimization

**Indexes:**
```sql
CREATE INDEX idx_messages_breeder_id ON messages(breeder_id);
CREATE INDEX idx_messages_is_read ON messages(is_read);
CREATE INDEX idx_messages_sender_email ON messages(sender_email);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

**Query Optimization:**
- Pagination limits (max 100 records per request)
- Efficient WHERE clauses using indexed columns
- COUNT queries optimized with subqueries
- No N+1 query problems (proper joins)

**Connection Pooling:**
- SQLAlchemy async connection pool
- Configurable pool size
- Connection recycling

### API Optimization

**Response Times (Target):**
- Send message: < 200ms
- Get messages list: < 300ms
- Get unread count: < 100ms
- Mark as read: < 150ms
- Send response: < 200ms

**Caching Strategy:**
- Unread count cached for 30 seconds (client-side)
- Message list cached until mutation
- No server-side caching (real-time data)

### Frontend Optimization

**Lazy Loading:**
- Components loaded on-demand
- Routes use lazy loading
- Images lazy-loaded

**Polling Optimization:**
- 30-second interval (configurable)
- Polling stops when component destroyed
- Debounced API calls

**Bundle Optimization:**
- Tree-shaking removes unused code
- Minification in production
- Code splitting by route


## Scalability Considerations

### Horizontal Scaling

**Backend:**
- Stateless API design
- No session storage on server
- Can run multiple instances behind load balancer
- Database connection pooling per instance

**Database:**
- PostgreSQL supports read replicas
- Write operations go to primary
- Read operations can use replicas
- Partitioning possible for large message volumes

### Vertical Scaling

**Database:**
- Increase memory for query caching
- Increase CPU for concurrent queries
- SSD storage for faster I/O

**Backend:**
- Increase worker processes
- Increase memory for larger connection pools

### Future Enhancements

**Caching Layer:**
- Redis for unread counts
- Cache invalidation on message mutations
- Session storage for high-traffic scenarios

**Message Queue:**
- Async message processing
- Email notifications via queue
- Batch operations

**CDN:**
- Static assets served from CDN
- Reduced server load
- Faster global access


## Error Handling

### Backend Error Responses

**HTTP Status Codes:**
- `200 OK`: Successful GET/PATCH/POST
- `201 Created`: Message successfully sent
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Message or breeder not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

**Error Response Format:**
```json
{
  "detail": "Error message description"
}
```

### Frontend Error Handling

**Service Layer:**
- HTTP errors caught and logged
- User-friendly error messages
- Toast notifications for errors

**Component Layer:**
- Loading states during API calls
- Error states displayed to user
- Retry mechanisms where appropriate

**Global Error Handler:**
- Catches uncaught errors
- Logs to console (dev) or error service (prod)
- Displays generic error message to user


## Testing Strategy

### Backend Tests

**Unit Tests:**
- Message model tests (12 tests)
- Message schema tests (28 tests)
- Test fixtures for reusable data
- Isolated database per test

**Integration Tests:**
- API endpoint tests (29 tests)
- Authentication/authorization tests
- Validation tests
- Database transaction tests

**Test Coverage:**
- 100% coverage for message-related code
- 55% overall backend coverage

### Frontend Tests

**Service Tests:**
- MessageService unit tests (19 tests)
- HTTP mocking with HttpClientTestingModule
- Error scenario testing
- All service methods tested

**Component Tests:**
- Deferred due to Angular 21 migration
- Can be added in future sprint

**E2E Tests:**
- Not implemented (optional)
- Would test complete user flows

### Test Execution

**Backend:**
```bash
cd pets.backend.dev/fastapi-backend
python -m pytest tests/ -v
python -m pytest tests/ --cov=app --cov-report=html
```

**Frontend:**
```bash
cd pets.frontend.dev
npm test -- --include='**/message.service.spec.ts' --watch=false
```


## Deployment Architecture

### Development Environment

**Backend:**
```bash
cd pets.backend.dev/fastapi-backend
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd pets.frontend.dev
ng serve --port 4200
```

**Database:**
```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=pets_db \
  -p 5432:5432 \
  postgres:13
```

### Production Environment

**Backend:**
- Deployed as Docker container or systemd service
- Multiple workers (e.g., 4 workers)
- Behind reverse proxy (nginx)
- HTTPS enabled
- Environment variables for configuration

**Frontend:**
- Built with `ng build --configuration production`
- Served by nginx or CDN
- Minified and optimized
- HTTPS enabled

**Database:**
- Managed PostgreSQL service (e.g., AWS RDS, Azure Database)
- Automated backups
- Read replicas for scaling
- Connection pooling

### Environment Variables

**Backend (.env):**
```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**Frontend (environment.ts):**
```typescript
export const environment = {
  production: true,
  apiUrl: 'https://api.example.com'
};
```


## Monitoring & Observability

### Logging

**Backend Logging:**
```python
import logging
logger = logging.getLogger(__name__)

# Log levels used:
logger.info("New message created")      # Normal operations
logger.warning("Invalid email format")  # Warnings
logger.error("Database error")          # Errors
```

**Log Locations:**
- Development: Console output
- Production: Log files + centralized logging (e.g., CloudWatch, Datadog)

### Metrics to Monitor

**Application Metrics:**
- API request rate
- API response times
- Error rates by endpoint
- Active user sessions

**Database Metrics:**
- Query execution times
- Connection pool usage
- Table sizes
- Index usage

**Business Metrics:**
- Messages sent per day
- Average response time
- Response rate
- Unread message count

### Health Checks

**Backend Health Endpoint:**
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**Database Health:**
```python
@app.get("/health/db")
async def db_health_check(session: AsyncSession):
    await session.execute("SELECT 1")
    return {"status": "healthy"}
```


## Future Enhancements

### Planned Features

1. **Email Notifications**
   - Send email to breeder on new message
   - Send email to sender on response
   - Configurable notification preferences

2. **Real-time Updates**
   - WebSocket connection for instant notifications
   - Live message updates without polling
   - Typing indicators

3. **Message Management**
   - Archive old messages
   - Delete messages
   - Mark multiple as read
   - Bulk operations

4. **Advanced Features**
   - Message search functionality
   - Message threading/conversations
   - Attachment support (images, documents)
   - Message templates for common responses
   - Auto-responses for common questions

5. **Spam Prevention**
   - CAPTCHA on contact form
   - Rate limiting (5 messages/hour per IP)
   - Block/report spam functionality
   - Spam detection algorithms

6. **Analytics**
   - Response time analytics
   - Message volume trends
   - Conversion tracking
   - User engagement metrics

### Technical Improvements

1. **Performance**
   - Redis caching layer
   - Database query optimization
   - CDN for static assets
   - Image optimization

2. **Scalability**
   - Message queue for async processing
   - Database sharding
   - Microservices architecture
   - Load balancing

3. **Security**
   - Two-factor authentication
   - IP-based rate limiting
   - Advanced spam filtering
   - Audit logging

4. **Testing**
   - E2E test suite
   - Performance testing
   - Load testing
   - Security testing

---

**Document Version**: 1.0  
**Last Updated**: February 11, 2026  
**Maintained By**: Development Team
