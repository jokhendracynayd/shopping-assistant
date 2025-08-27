"""Session management service for shopping assistant.

Provides session-based features:
- Conversation memory and context
- User preferences and shopping cart
- Session-specific caching
- Analytics and personalization
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from app.database.redis_client import get_redis_client
from app.utils.logger import get_logger

logger = get_logger("services.session")


class SessionService:
    """Manages user sessions and conversation state."""
    
    def __init__(self):
        self.redis = None  # Will be initialized in async methods
        self.session_ttl = 3600 * 24  # 24 hours
        self.conversation_ttl = 3600 * 2  # 2 hours for conversation history
    
    async def _get_redis_client(self):
        """Get Redis client, initializing if needed."""
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis
    
    async def _get_session_key(self, session_id: str, key_type: str) -> str:
        """Generate Redis key for session data."""
        return f"session:{session_id}:{key_type}"
    
    async def create_session(self, session_id: str, user_data: Optional[Dict[str, Any]] = None) -> bool:
        """Create a new user session."""
        try:
            redis_client = await self._get_redis_client()
            session_key = await self._get_session_key(session_id, "info")
            session_data = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
                "user_data": user_data or {},
                "conversation_count": 0,
                "preferences": {},
                "shopping_cart": []
            }
            
            await redis_client.setex(
                session_key, 
                self.session_ttl, 
                json.dumps(session_data)
            )
            
            logger.info(f"Created new session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session {session_id}: {e}")
            return False
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        try:
            redis_client = await self._get_redis_client()
            session_key = await self._get_session_key(session_id, "info")
            data = await redis_client.get(session_key)
            
            if data:
                session_data = json.loads(data)
                # Update last active
                session_data["last_active"] = datetime.now(timezone.utc).isoformat()
                await redis_client.setex(session_key, self.session_ttl, json.dumps(session_data))
                return session_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get session info for {session_id}: {e}")
            return None
    
    async def add_conversation_message(self, session_id: str, role: str, content: str) -> bool:
        """Add a message to conversation history."""
        try:
            redis_client = await self._get_redis_client()
            conv_key = await self._get_session_key(session_id, "conversation")
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Add to conversation list
            await redis_client.lpush(conv_key, json.dumps(message))
            await redis_client.expire(conv_key, self.conversation_ttl)
            
            # Update session info
            session_key = await self._get_session_key(session_id, "info")
            session_data = await self.get_session_info(session_id)
            if session_data:
                session_data["conversation_count"] += 1
                await redis_client.setex(session_key, self.session_ttl, json.dumps(session_data))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add conversation message for {session_id}: {e}")
            return False
    
    async def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history."""
        try:
            redis_client = await self._get_redis_client()
            conv_key = await self._get_session_key(session_id, "conversation")
            messages = await redis_client.lrange(conv_key, 0, limit - 1)
            
            conversation = []
            for msg in reversed(messages):  # Reverse to get chronological order
                try:
                    conversation.append(json.loads(msg))
                except json.JSONDecodeError:
                    continue
            
            return conversation
            
        except Exception as e:
            logger.error(f"Failed to get conversation history for {session_id}: {e}")
            return []
    
    async def update_user_preferences(self, session_id: str, preferences: Dict[str, Any]) -> bool:
        """Update user preferences for the session."""
        try:
            redis_client = await self._get_redis_client()
            session_data = await self.get_session_info(session_id)
            if not session_data:
                return False
            
            # Merge new preferences
            session_data["preferences"].update(preferences)
            session_data["last_active"] = datetime.now(timezone.utc).isoformat()
            
            session_key = await self._get_session_key(session_id, "info")
            await redis_client.setex(session_key, self.session_ttl, json.dumps(session_data))
            
            logger.info(f"Updated preferences for session {session_id}: {preferences}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update preferences for {session_id}: {e}")
            return False
    
    async def add_to_cart(self, session_id: str, item: Dict[str, Any]) -> bool:
        """Add item to shopping cart."""
        try:
            redis_client = await self._get_redis_client()
            session_data = await self.get_session_info(session_id)
            if not session_data:
                return False
            
            # Add item with timestamp
            item["added_at"] = datetime.now(timezone.utc).isoformat()
            session_data["shopping_cart"].append(item)
            session_data["last_active"] = datetime.now(timezone.utc).isoformat()
            
            session_key = await self._get_session_key(session_id, "info")
            await redis_client.setex(session_key, self.session_ttl, json.dumps(session_data))
            
            logger.info(f"Added item to cart for session {session_id}: {item.get('name', 'Unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add item to cart for {session_id}: {e}")
            return False
    
    async def get_shopping_cart(self, session_id: str) -> List[Dict[str, Any]]:
        """Get current shopping cart."""
        try:
            session_data = await self.get_session_info(session_id)
            return session_data.get("shopping_cart", []) if session_data else []
            
        except Exception as e:
            logger.error(f"Failed to get shopping cart for {session_id}: {e}")
            return []
    
    async def clear_cart(self, session_id: str) -> bool:
        """Clear shopping cart."""
        try:
            redis_client = await self._get_redis_client()
            session_data = await self.get_session_info(session_id)
            if not session_data:
                return False
            
            session_data["shopping_cart"] = []
            session_data["last_active"] = datetime.now(timezone.utc).isoformat()
            
            session_key = await self._get_session_key(session_id, "info")
            await redis_client.setex(session_key, self.session_ttl, json.dumps(session_data))
            
            logger.info(f"Cleared cart for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cart for {session_id}: {e}")
            return False
    
    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get analytics for the session."""
        try:
            session_data = await self.get_session_info(session_id)
            if not session_data:
                return {}
            
            conversation = await self.get_conversation_history(session_id, limit=100)
            
            # Analyze conversation patterns
            user_messages = [msg for msg in conversation if msg["role"] == "user"]
            assistant_messages = [msg for msg in conversation if msg["role"] == "assistant"]
            
            # Extract common topics (simple keyword analysis)
            common_words = []
            for msg in user_messages:
                words = msg["content"].lower().split()
                common_words.extend([w for w in words if len(w) > 3])
            
            word_freq = {}
            for word in common_words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            top_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                "session_duration": self._calculate_session_duration(session_data),
                "conversation_count": session_data.get("conversation_count", 0),
                "user_message_count": len(user_messages),
                "assistant_message_count": len(assistant_messages),
                "cart_item_count": len(session_data.get("shopping_cart", [])),
                "top_topics": [{"word": word, "count": count} for word, count in top_topics],
                "preferences": session_data.get("preferences", {}),
                "last_active": session_data.get("last_active")
            }
            
        except Exception as e:
            logger.error(f"Failed to get analytics for {session_id}: {e}")
            return {}
    
    def _calculate_session_duration(self, session_data: Dict[str, Any]) -> Optional[str]:
        """Calculate session duration."""
        try:
            created_at = datetime.fromisoformat(session_data["created_at"])
            last_active = datetime.fromisoformat(session_data["last_active"])
            duration = last_active - created_at
            
            if duration.days > 0:
                return f"{duration.days}d {duration.seconds // 3600}h"
            elif duration.seconds > 3600:
                return f"{duration.seconds // 3600}h {(duration.seconds % 3600) // 60}m"
            else:
                return f"{duration.seconds // 60}m"
                
        except Exception:
            return None
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (called periodically)."""
        try:
            # This would be implemented with a background task
            # For now, Redis TTL handles expiration automatically
            return 0
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0


# Global instance
session_service = SessionService()
