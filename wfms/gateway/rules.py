"""
Gateway Rules Engine

Implements rate limiting and command validation:
- Global lock: reject all commands when enabled
- Per-user cooldown: prevent spam from single user
- Global cooldown: minimum gap between any commands
- CID deduplication: reject duplicate command IDs within TTL
"""

import time
import threading
import logging
from typing import Tuple, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RulesConfig:
    """Rules configuration (from gateway Config)."""
    lock: bool = False
    cooldown_user_s: int = 3
    cooldown_global_s: int = 1
    dedupe_ttl_s: int = 60


class Rules:
    """
    Rules engine for command validation.
    Thread-safe implementation.
    """
    
    def __init__(self, config: RulesConfig):
        self.config = config
        
        self._lock = threading.Lock()
        
        # Track last command time per user
        self._user_last_cmd: Dict[str, float] = {}
        
        # Track global last command time
        self._global_last_cmd: float = 0.0
        
        # Track seen CIDs with expiration time
        self._seen_cids: Dict[str, float] = {}
        
        # Cleanup interval
        self._last_cleanup: float = time.time()
        self._cleanup_interval: float = 30.0
    
    def update_config(self, config: RulesConfig) -> None:
        """Update rules configuration (hot reload)."""
        with self._lock:
            self.config = config
            logger.info(f"Rules config updated: lock={config.lock}, "
                       f"cooldown_user={config.cooldown_user_s}s, "
                       f"cooldown_global={config.cooldown_global_s}s")
    
    def check_and_mark(self, cid: str, user: str) -> Tuple[bool, str]:
        """
        Check if command is allowed and mark it if so.
        
        Args:
            cid: Command ID (must be unique)
            user: User ID who sent the command
        
        Returns:
            Tuple of (allowed, reason):
            - allowed: True if command should proceed
            - reason: Empty string if allowed, otherwise one of:
                "locked", "duplicate_cid", "cooldown_user", "cooldown_global"
        """
        now = time.time()
        
        with self._lock:
            # Periodic cleanup
            self._maybe_cleanup(now)
            
            # Check global lock
            if self.config.lock:
                logger.debug(f"Command {cid} rejected: global lock enabled")
                return (False, "locked")
            
            # Check CID duplication
            if cid in self._seen_cids:
                if self._seen_cids[cid] > now:
                    logger.debug(f"Command {cid} rejected: duplicate CID")
                    return (False, "duplicate_cid")
            
            # Check user cooldown
            if user in self._user_last_cmd:
                elapsed = now - self._user_last_cmd[user]
                if elapsed < self.config.cooldown_user_s:
                    remaining = self.config.cooldown_user_s - elapsed
                    logger.debug(f"Command {cid} rejected: user cooldown ({remaining:.1f}s remaining)")
                    return (False, "cooldown_user")
            
            # Check global cooldown
            elapsed_global = now - self._global_last_cmd
            if elapsed_global < self.config.cooldown_global_s:
                remaining = self.config.cooldown_global_s - elapsed_global
                logger.debug(f"Command {cid} rejected: global cooldown ({remaining:.1f}s remaining)")
                return (False, "cooldown_global")
            
            # All checks passed - mark this command
            self._seen_cids[cid] = now + self.config.dedupe_ttl_s
            self._user_last_cmd[user] = now
            self._global_last_cmd = now
            
            logger.debug(f"Command {cid} from user {user} allowed")
            return (True, "")
    
    def _maybe_cleanup(self, now: float) -> None:
        """Clean up expired entries (called while holding lock)."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = now
        
        # Remove expired CIDs
        expired_cids = [
            cid for cid, exp_time in self._seen_cids.items()
            if exp_time <= now
        ]
        for cid in expired_cids:
            del self._seen_cids[cid]
        
        # Remove stale user entries (older than 10x cooldown)
        stale_threshold = now - (self.config.cooldown_user_s * 10)
        stale_users = [
            user for user, last_time in self._user_last_cmd.items()
            if last_time < stale_threshold
        ]
        for user in stale_users:
            del self._user_last_cmd[user]
        
        if expired_cids or stale_users:
            logger.debug(f"Rules cleanup: removed {len(expired_cids)} CIDs, {len(stale_users)} users")
    
    def reset(self) -> None:
        """Reset all tracked state (for testing)."""
        with self._lock:
            self._user_last_cmd.clear()
            self._global_last_cmd = 0.0
            self._seen_cids.clear()
            logger.info("Rules state reset")
    
    @property
    def stats(self) -> dict:
        """Get current rules statistics."""
        with self._lock:
            return {
                "lock": self.config.lock,
                "tracked_users": len(self._user_last_cmd),
                "tracked_cids": len(self._seen_cids),
                "cooldown_user_s": self.config.cooldown_user_s,
                "cooldown_global_s": self.config.cooldown_global_s,
                "dedupe_ttl_s": self.config.dedupe_ttl_s,
            }
