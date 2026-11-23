"""Compatibility facade for the shared conversation store."""
import os
from conversation import ConversationService
DB_PATH = os.environ.get("KATER_DB_PATH", "kater.db")
service = ConversationService(DB_PATH, owner_id=int(os.environ["OWNER_TELEGRAM_ID"]))
load_history = service.load_history
clear_history = service.clear_history
