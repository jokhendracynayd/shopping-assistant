# Session Management Guide

## Overview

The Shopping Assistant now includes comprehensive session management capabilities that leverage the `sessionId` parameter to provide personalized, contextual shopping experiences.

## 🎯 What You Can Do With SessionId

### 1. **Conversation Memory & Context**
- **Persistent Chat History**: Every message is stored and can be referenced in future conversations
- **Context Awareness**: The AI remembers previous questions and can provide more relevant follow-up responses
- **Session Continuity**: Users can continue conversations across multiple API calls

### 2. **Personalized Shopping Experience**
- **User Preferences**: Store and retrieve user preferences (budget, brand preferences, device types)
- **Shopping Cart**: Maintain cart state across chat sessions
- **Purchase History**: Reference previous interactions and recommendations

### 3. **Session-Based Analytics**
- **Conversation Patterns**: Track how users interact with the assistant
- **Topic Analysis**: Identify common themes and interests
- **Engagement Metrics**: Monitor session duration and message counts

### 4. **Smart Caching & Performance**
- **Response Caching**: Cache responses per session to avoid expensive LLM calls
- **Context Window Management**: Maintain conversation context within session limits
- **RAG Context Persistence**: Remember relevant documents for follow-up questions

## 🚀 API Endpoints

### Core Shopping Endpoints (Enhanced)

#### POST `/api/v1/shopping/query`
**Enhanced with session management:**
- Automatically creates/retrieves session
- Stores user questions and AI responses
- Maintains conversation context

```json
{
  "q": "What smartphones do you have?",
  "sessionId": "user-123-session-456"
}
```

#### POST `/api/v1/shopping/query/stream`
**Enhanced with session management:**
- Same session features as regular query
- Streaming responses with session tracking

### New Session Management Endpoints

#### GET `/api/v1/shopping/session/{session_id}/info`
Get comprehensive session information and analytics.

**Response:**
```json
{
  "success": true,
  "data": {
    "session_info": {
      "created_at": "2024-01-15T10:30:00Z",
      "last_active": "2024-01-15T11:45:00Z",
      "conversation_count": 5,
      "preferences": {
        "budget_range": "500-1000",
        "preferred_brands": ["Apple", "Samsung"]
      },
      "shopping_cart": []
    },
    "analytics": {
      "session_duration": "1h 15m",
      "user_message_count": 3,
      "assistant_message_count": 2,
      "top_topics": [
        {"word": "smartphone", "count": 3},
        {"word": "camera", "count": 2}
      ]
    }
  }
}
```

#### GET `/api/v1/shopping/session/{session_id}/conversation`
Get conversation history for a session.

**Query Parameters:**
- `limit` (optional): Number of messages to retrieve (default: 20)

**Response:**
```json
{
  "success": true,
  "data": {
    "session_id": "user-123-session-456",
    "conversation": [
      {
        "role": "user",
        "content": "What smartphones do you have?",
        "timestamp": "2024-01-15T10:30:00Z"
      },
      {
        "role": "assistant",
        "content": "We offer several smartphone models...",
        "timestamp": "2024-01-15T10:30:05Z"
      }
    ],
    "count": 2
  }
}
```

#### POST `/api/v1/shopping/session/{session_id}/preferences`
Update user preferences for a session.

**Request Body:**
```json
{
  "budget_range": "500-1000",
  "preferred_brands": ["Apple", "Samsung"],
  "device_type": "smartphone",
  "shipping_preference": "express"
}
```

#### GET `/api/v1/shopping/session/{session_id}/cart`
Get current shopping cart contents.

#### POST `/api/v1/shopping/session/{session_id}/cart/add`
Add item to shopping cart.

**Request Body:**
```json
{
  "name": "iPhone 15 Pro",
  "price": 999,
  "category": "smartphone",
  "sku": "IPH15PRO-256"
}
```

#### DELETE `/api/v1/shopping/session/{session_id}/cart/clear`
Clear shopping cart for a session.

## 💡 Best Practices

### 1. **Session ID Generation**
- Use unique, persistent identifiers (UUIDs, user IDs + timestamps)
- Avoid sequential or predictable IDs for security
- Consider user privacy and GDPR compliance

### 2. **Session Lifecycle**
- Sessions automatically expire after 24 hours of inactivity
- Conversation history expires after 2 hours
- Implement session cleanup for production environments

### 3. **Error Handling**
- Always check if session exists before operations
- Handle session expiration gracefully
- Provide fallback responses for missing sessions

### 4. **Performance Optimization**
- Use session-based caching for frequently asked questions
- Implement lazy loading for conversation history
- Consider pagination for long conversation histories

## 🔧 Implementation Examples

### Frontend Integration

```javascript
// Initialize session
const sessionId = generateSessionId();
const session = await initializeSession(sessionId);

// Send query with session
const response = await fetch('/api/v1/shopping/query', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    q: "What smartphones do you have?",
    sessionId: sessionId
  })
});

// Get session analytics
const analytics = await fetch(`/api/v1/shopping/session/${sessionId}/info`);
```

### Backend Integration

```python
from app.services.session_service import session_service

# Get session info
session_info = await session_service.get_session_info(session_id)

# Add conversation message
await session_service.add_conversation_message(session_id, "user", question)

# Update preferences
await session_service.update_user_preferences(session_id, {
    "budget_range": "500-1000",
    "preferred_brands": ["Apple"]
})
```

## 📊 Analytics & Insights

### Session Metrics
- **Duration**: How long users stay engaged
- **Conversation Count**: Number of message exchanges
- **Topic Analysis**: Common themes and interests
- **Cart Behavior**: Items added, removed, purchased

### Business Intelligence
- **User Journey Mapping**: How users progress through shopping decisions
- **Conversion Tracking**: What drives users to make purchases
- **Preference Patterns**: Understanding user segments
- **Engagement Optimization**: Improving user experience

## 🔒 Security Considerations

### Data Privacy
- Session data is stored in Redis with TTL expiration
- No persistent storage of sensitive information
- Consider implementing data anonymization for analytics

### Access Control
- Validate session ownership before operations
- Implement rate limiting per session
- Monitor for suspicious session patterns

### Compliance
- GDPR compliance for EU users
- Data retention policies
- User consent for analytics collection

## 🚀 Future Enhancements

### Planned Features
- **Cross-Session Learning**: Apply insights across multiple sessions
- **Advanced Analytics**: Machine learning-based pattern recognition
- **Real-time Notifications**: Session-based alerts and recommendations
- **Integration APIs**: Connect with external CRM and analytics systems

### Advanced Use Cases
- **A/B Testing**: Test different conversation flows per session
- **Personalization Engine**: Dynamic content based on session history
- **Predictive Analytics**: Anticipate user needs based on patterns
- **Multi-modal Sessions**: Support for voice, text, and image inputs

## 📝 Troubleshooting

### Common Issues

#### Session Not Found
- Check if session ID is correct
- Verify session hasn't expired
- Ensure Redis is running and accessible

#### Conversation History Missing
- Check conversation TTL settings
- Verify Redis list operations
- Monitor Redis memory usage

#### Performance Issues
- Implement connection pooling
- Use Redis pipelining for batch operations
- Monitor Redis latency and throughput

### Debug Commands

```bash
# Check Redis session data
redis-cli keys "session:*"

# View specific session
redis-cli get "session:user-123-session-456:info"

# Check conversation history
redis-cli lrange "session:user-123-session-456:conversation" 0 -1
```

## 📚 Additional Resources

- [Redis Documentation](https://redis.io/documentation)
- [FastAPI Session Management](https://fastapi.tiangolo.com/tutorial/security/)
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/)
- [Session Management Best Practices](https://owasp.org/www-project-proactive-controls/v3/en/c5-validate-inputs)


�� Next Steps
Test the Demo: Run python examples/session_demo.py
Integrate Frontend: Use the new API endpoints in your UI
Monitor Analytics: Track session metrics and user engagement
Customize: Adapt the session service for your specific needs
Your sessionId is now a powerful key that unlocks:
🧠 Memory - Remember everything about the user
🛒 Context - Maintain shopping state
📈 Insights - Understand user behavior
🎨 Personalization - Tailor experiences