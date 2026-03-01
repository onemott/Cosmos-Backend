import json
from typing import Dict, List, Any
from fastapi import WebSocket
from src.core.logging import get_logger

logger = get_logger(__name__)

class ConnectionManager:
    """Manages WebSocket connections for chat."""

    def __init__(self):
        # Map user_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept connection and add to active connections."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected via WebSocket. Device count: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove connection."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected from WebSocket.")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send JSON message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast(self, message: dict, user_ids: List[str]):
        """Broadcast JSON message to specific users (all their devices)."""
        logger.info(f"Broadcasting to user_ids: {user_ids}")
        logger.info(f"Active connections: {list(self.active_connections.keys())}")
        
        sent_count = 0
        for user_id in user_ids:
            if user_id in self.active_connections:
                connections = self.active_connections[user_id]
                logger.info(f"Found active connection for user {user_id} (count: {len(connections)}), sending message...")
                for connection in connections[:]:
                    try:
                        await connection.send_json(message)
                        sent_count += 1
                        logger.info(f"Message sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Error sending message to user {user_id}: {e}")
                        # Cleanup dead connection?
            else:
                logger.debug(f"No active connection found for user {user_id}")
        
        logger.info(f"Broadcast complete. Sent {sent_count} messages.")

chat_manager = ConnectionManager()
