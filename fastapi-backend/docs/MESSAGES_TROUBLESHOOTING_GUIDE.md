# Breeder Messages - Troubleshooting Guide

## Overview

This guide provides technical troubleshooting steps for common issues with the Breeder Messages system. It's intended for developers, system administrators, and technical support staff.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Common Issues](#common-issues)
3. [Backend Troubleshooting](#backend-troubleshooting)
4. [Frontend Troubleshooting](#frontend-troubleshooting)
5. [Database Issues](#database-issues)
6. [Performance Issues](#performance-issues)
7. [Monitoring & Logging](#monitoring--logging)
8. [Emergency Procedures](#emergency-procedures)

---

## System Architecture

### Components

**Backend (FastAPI + PostgreSQL)**
- API Router: `app/routers/messages.py`
- Model: `app/models/message.py`
- Schemas: `app/schemas/message.py`
- Database: PostgreSQL with `messages` table

**Frontend (Angular)**
- Service: `src/app/services/message.service.ts`
- Components:
  - `contact-breeder` - Anonymous contact form
  - `notification-icon` - Unread count badge
  - `messages-list` - Message inbox
  - `message-detail` - Message view/response

### Data Flow

```
Anonymous User → Contact Form → POST /api/messages/send → Database
Database → GET /api/messages/ → Messages List → Breeder
Breeder → Response Form → POST /api/messages/{id}/respond → Database
```

---

## Common Issues

### Issue 1: Messages Not Sending

**Symptoms:**
- Contact form submission fails
- Error toast appears
- No message created in database

**Diagnosis:**

1. Check browser console for errors:
```javascript
// Look for HTTP errors
Failed to load resource: the server responded with a status of 404
```

2. Check backend logs:
```bash
tail -f logs/app.log | grep "messages"
```

3. Verify breeder exists:
```sql
SELECT id, email FROM users WHERE id = 'breeder-uuid';
```

**Solutions:**

- **404 Error**: Breeder ID doesn't exist
  - Verify the breeder_id being sent
  - Check that the breeder account is active
  
- **422 Validation Error**: Invalid data
  - Check email format validation
  - Verify all required fields are present
  - Check character limits (name: 255, message: 2000)

- **500 Server Error**: Backend issue
  - Check database connectivity
  - Review backend logs for stack traces
  - Verify database schema is up to date

### Issue 2: Notification Count Not Updating

**Symptoms:**
- Badge shows incorrect count
- Count doesn't update after reading messages
- Badge doesn't appear when new messages arrive

**Diagnosis:**

1. Check polling interval:
```typescript
// In notification-icon.component.ts
// Should poll every 30 seconds
```

2. Check API response:
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/messages/unread-count
```

3. Check database count:
```sql
SELECT COUNT(*) FROM messages 
WHERE breeder_id = 'user-uuid' AND is_read = false;
```

**Solutions:**

- **Polling stopped**: Component destroyed or error occurred
  - Check browser console for errors
  - Verify component lifecycle hooks
  - Check that user is still authenticated

- **Count mismatch**: Database and API out of sync
  - Refresh the page
  - Check for database transaction issues
  - Verify mark-as-read functionality

- **Badge not visible**: CSS or rendering issue
  - Check browser developer tools
  - Verify badge element exists in DOM
  - Check CSS z-index and positioning

### Issue 3: Messages Not Loading

**Symptoms:**
- Empty messages list
- Loading spinner never stops
- Error message displayed

**Diagnosis:**

1. Check API endpoint:
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/messages/?status=all&limit=20&offset=0"
```

2. Check authentication:
```typescript
// Verify token is present and valid
localStorage.getItem('access_token')
```

3. Check database:
```sql
SELECT * FROM messages WHERE breeder_id = 'user-uuid' LIMIT 5;
```

**Solutions:**

- **401 Unauthorized**: Authentication issue
  - User needs to log in again
  - Token may have expired
  - Check token refresh logic

- **Empty response**: No messages exist
  - This is normal for new accounts
  - Verify empty state is displayed correctly

- **Timeout**: Slow query or network issue
  - Check database query performance
  - Verify indexes exist on messages table
  - Check network connectivity

### Issue 4: Response Not Saving

**Symptoms:**
- Response form submission fails
- Error toast appears
- Response not visible after submission

**Diagnosis:**

1. Check API call:
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"response_text":"Test response"}' \
  http://localhost:8000/api/messages/{message-id}/respond
```

2. Check validation:
```typescript
// Response must be 1-5000 characters
response_text.length >= 1 && response_text.length <= 5000
```

3. Check database:
```sql
SELECT response_text, responded_at FROM messages WHERE id = 'message-uuid';
```

**Solutions:**

- **422 Validation Error**: Invalid response text
  - Check character count (1-5000)
  - Verify text is not empty
  - Check for special characters causing issues

- **404 Not Found**: Message doesn't exist or wrong breeder
  - Verify message ID is correct
  - Check that message belongs to authenticated breeder

- **500 Server Error**: Database or backend issue
  - Check backend logs
  - Verify database connectivity
  - Check for database constraints

---

## Backend Troubleshooting

### Database Connection Issues

**Check connection:**
```python
# In Python shell
from app.database import get_async_session
async for session in get_async_session():
    result = await session.execute("SELECT 1")
    print(result.scalar())
```

**Common fixes:**
- Verify DATABASE_URL environment variable
- Check PostgreSQL is running: `pg_isready`
- Verify database credentials
- Check network connectivity to database

### Migration Issues

**Check current migration:**
```bash
cd pets.backend.dev/fastapi-backend
alembic current
```

**Apply pending migrations:**
```bash
alembic upgrade head
```

**Rollback if needed:**
```bash
alembic downgrade -1
```

### API Endpoint Issues

**Test endpoints manually:**
```bash
# Send message (public)
curl -X POST http://localhost:8000/api/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "breeder_id": "uuid",
    "sender_name": "Test User",
    "sender_email": "test@example.com",
    "message": "Test message"
  }'

# Get messages (protected)
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/messages/

# Get unread count (protected)
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/messages/unread-count

# Mark as read (protected)
curl -X PATCH \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/messages/{message-id}/read

# Respond (protected)
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"response_text":"Test response"}' \
  http://localhost:8000/api/messages/{message-id}/respond
```

### Logging

**Enable debug logging:**
```python
# In app/main.py or config
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check logs:**
```bash
# Application logs
tail -f logs/app.log

# Filter for messages
grep "message" logs/app.log

# Check for errors
grep "ERROR" logs/app.log
```

---

## Frontend Troubleshooting

### Service Issues

**Check service initialization:**
```typescript
// In browser console
// Service should be injected and available
```

**Test service methods:**
```typescript
// In browser console (if service is exposed)
messageService.getUnreadCount().subscribe(
  data => console.log('Unread count:', data),
  error => console.error('Error:', error)
);
```

### Component Issues

**Check component lifecycle:**
```typescript
// Add console.logs to lifecycle hooks
ngOnInit() {
  console.log('Component initialized');
}

ngOnDestroy() {
  console.log('Component destroyed');
}
```

**Check data binding:**
```html
<!-- Add debug output in template -->
<pre>{{ messages | json }}</pre>
```

### HTTP Interceptor Issues

**Check authentication:**
```typescript
// Verify token is being added to requests
// Check Network tab in browser DevTools
// Look for Authorization header
```

**Check error handling:**
```typescript
// Errors should be caught and displayed
// Check browser console for uncaught errors
```

### Routing Issues

**Verify routes:**
```typescript
// In app-routing.module.ts
// Check that routes are defined:
// /settings/messages
// /settings/messages/:id
```

**Test navigation:**
```typescript
// In browser console
this.router.navigate(['/settings/messages']);
```

---

## Database Issues

### Schema Verification

**Check table exists:**
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name = 'messages';
```

**Check columns:**
```sql
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'messages';
```

**Check indexes:**
```sql
SELECT indexname, indexdef FROM pg_indexes 
WHERE tablename = 'messages';
```

### Data Integrity

**Check for orphaned messages:**
```sql
SELECT m.* FROM messages m
LEFT JOIN users u ON m.breeder_id = u.id
WHERE u.id IS NULL;
```

**Check for invalid data:**
```sql
-- Invalid email formats
SELECT * FROM messages 
WHERE sender_email NOT LIKE '%@%.%';

-- Messages without sender name
SELECT * FROM messages 
WHERE sender_name IS NULL OR sender_name = '';
```

### Performance Queries

**Check slow queries:**
```sql
-- Enable query logging in postgresql.conf
log_min_duration_statement = 1000  -- Log queries > 1 second

-- Check pg_stat_statements
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
WHERE query LIKE '%messages%'
ORDER BY mean_exec_time DESC;
```

**Analyze query plans:**
```sql
EXPLAIN ANALYZE
SELECT * FROM messages 
WHERE breeder_id = 'uuid' AND is_read = false
ORDER BY created_at DESC
LIMIT 20;
```

---

## Performance Issues

### Slow API Responses

**Diagnosis:**

1. Check query execution time:
```sql
EXPLAIN ANALYZE <query>;
```

2. Check index usage:
```sql
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename = 'messages';
```

3. Check database connections:
```sql
SELECT count(*) FROM pg_stat_activity;
```

**Solutions:**

- **Missing indexes**: Add indexes on frequently queried columns
```sql
CREATE INDEX idx_messages_breeder_id ON messages(breeder_id);
CREATE INDEX idx_messages_is_read ON messages(is_read);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

- **Too many connections**: Increase connection pool size or add connection pooling

- **Large result sets**: Ensure pagination is working correctly

### High Memory Usage

**Check backend memory:**
```bash
ps aux | grep uvicorn
```

**Check database memory:**
```sql
SELECT * FROM pg_stat_database WHERE datname = 'your_database';
```

**Solutions:**
- Reduce pagination limit
- Add query result caching
- Optimize database queries
- Increase server resources

### Slow Frontend Loading

**Check bundle size:**
```bash
npm run build -- --stats-json
npx webpack-bundle-analyzer dist/stats.json
```

**Check network requests:**
- Open browser DevTools → Network tab
- Look for slow API calls
- Check for unnecessary requests

**Solutions:**
- Implement lazy loading for components
- Add caching for API responses
- Optimize images and assets
- Use CDN for static assets

---

## Monitoring & Logging

### Backend Monitoring

**Key metrics to monitor:**
- API response times
- Error rates
- Database query times
- Active connections
- Memory usage
- CPU usage

**Logging best practices:**
```python
# Log important events
logger.info(f"New message created: {message.id}")
logger.warning(f"Failed login attempt for user: {email}")
logger.error(f"Database error: {str(e)}")
```

### Frontend Monitoring

**Key metrics to monitor:**
- Page load times
- API call success rates
- JavaScript errors
- User interactions

**Error tracking:**
```typescript
// Implement global error handler
export class GlobalErrorHandler implements ErrorHandler {
  handleError(error: Error) {
    console.error('Global error:', error);
    // Send to error tracking service (e.g., Sentry)
  }
}
```

### Database Monitoring

**Key metrics:**
```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Long-running queries
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds';

-- Table size
SELECT pg_size_pretty(pg_total_relation_size('messages'));

-- Index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'messages';
```

---

## Emergency Procedures

### System Down

**Immediate actions:**
1. Check if backend is running: `curl http://localhost:8000/health`
2. Check database connectivity: `pg_isready`
3. Check logs for errors: `tail -100 logs/app.log`
4. Restart services if needed

**Recovery steps:**
```bash
# Restart backend
cd pets.backend.dev/fastapi-backend
pkill -f uvicorn
uvicorn app.main:app --reload

# Restart database (if needed)
sudo systemctl restart postgresql

# Clear caches
redis-cli FLUSHALL  # If using Redis
```

### Data Loss

**Backup restoration:**
```bash
# Restore from backup
pg_restore -d database_name backup_file.dump

# Verify data
psql -d database_name -c "SELECT COUNT(*) FROM messages;"
```

**Partial data loss:**
```sql
-- Check for missing data
SELECT * FROM messages WHERE created_at > 'timestamp' ORDER BY created_at;

-- Restore from transaction log if available
```

### Security Breach

**Immediate actions:**
1. Disable affected endpoints
2. Revoke all active tokens
3. Change database credentials
4. Review access logs
5. Notify affected users

**Investigation:**
```sql
-- Check for suspicious activity
SELECT * FROM messages 
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;

-- Check for mass deletions
SELECT * FROM pg_stat_user_tables WHERE tablename = 'messages';
```

---

## Diagnostic Checklist

### When investigating issues:

- [ ] Check browser console for JavaScript errors
- [ ] Check Network tab for failed API calls
- [ ] Check backend logs for errors
- [ ] Verify database connectivity
- [ ] Check authentication/authorization
- [ ] Verify data exists in database
- [ ] Check for recent code changes
- [ ] Verify environment variables
- [ ] Check server resources (CPU, memory, disk)
- [ ] Test in different browser
- [ ] Test with different user account
- [ ] Check for ongoing maintenance or deployments

---

## Contact & Escalation

### Support Levels

**Level 1**: User-facing issues
- Contact: support@example.com
- Response time: 24 hours

**Level 2**: Technical issues
- Contact: tech-support@example.com
- Response time: 4 hours

**Level 3**: Critical system issues
- Contact: emergency@example.com
- Response time: 1 hour

### Escalation Criteria

**Immediate escalation:**
- System completely down
- Data loss or corruption
- Security breach
- Multiple users affected

**Standard escalation:**
- Feature not working for single user
- Performance degradation
- Non-critical bugs

---

**Last Updated**: February 11, 2026  
**Version**: 1.0
