"""
Redis Coordinator

Provides distributed coordination using Redis with connection pooling, retry logic,
and resilience features. This is the foundation for leader election, heartbeat,
and signal-level locking (to be implemented in later tasks).

Key Features:
- Connection pooling for efficient resource management
- Retry logic with exponential backoff
- Fallback mode support (preparation for database-only mode)
- Health checking via ping()
"""
import redis
from redis.connection import ConnectionPool
import uuid
import time
import logging
import os
import threading
import socket
from typing import Optional
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class CoordinatorMetrics:
    """
    Track Redis coordinator metrics for monitoring and alerting
    
    **Alert Thresholds:**
    
    The following thresholds are defined for critical metrics:
    
    1. **DB Sync Failure Rate:**
       - WARNING: >5% failure rate (indicates degraded DB connectivity)
       - CRITICAL: >10% failure rate (indicates serious DB issues)
    
    2. **Leadership Change Frequency:**
       - WARNING: >3 changes per hour (indicates leadership flapping)
       - CRITICAL: >10 changes per hour (indicates severe instability)
    
    3. **Heartbeat Staleness:**
       - WARNING: No heartbeat for >30 seconds (indicates instance may be down)
       - CRITICAL: No heartbeat for >60 seconds (indicates instance is likely down)
    
    **Rolling Window Aggregation Algorithm:**
    
    This class uses a fixed-size rolling window (deque with maxlen=100) to maintain
    the last 100 latency samples. The rolling window provides:
    
    1. **Automatic Eviction**: When the window is full (100 samples), adding a new
       sample automatically removes the oldest sample (FIFO behavior).
    
    2. **Memory Efficiency**: Fixed memory footprint regardless of total samples
       collected over time.
    
    3. **Recent Focus**: Only the most recent 100 samples are considered for
       statistical calculations, providing a "recent performance" view.
    
    4. **Statistical Calculations**:
       - **Average (Mean)**: Sum of all samples / sample count
       - **Min/Max**: Minimum and maximum values in the window
       - **Percentiles (p50, p95, p99)**: Calculated using sorted sample array
         - p50 (median): 50th percentile - half of samples are below this value
         - p95: 95th percentile - 95% of samples are below this value (outlier threshold)
         - p99: 99th percentile - 99% of samples are below this value (extreme outliers)
    
    **Thread Safety:**
    All operations are protected by `_lock` to ensure thread-safe updates and reads
    in a multi-threaded environment (heartbeat loop, signal processing, etc.).
    """
    
    # Alert threshold constants
    DB_SYNC_FAILURE_RATE_WARNING = 0.05  # 5% - triggers WARNING
    DB_SYNC_FAILURE_RATE_CRITICAL = 0.10  # 10% - triggers CRITICAL
    LEADERSHIP_CHANGES_WARNING_PER_HOUR = 3  # >3 changes/hour - triggers WARNING
    LEADERSHIP_CHANGES_CRITICAL_PER_HOUR = 10  # >10 changes/hour - triggers CRITICAL
    HEARTBEAT_STALE_WARNING_SECONDS = 30  # >30s since last heartbeat - triggers WARNING
    HEARTBEAT_STALE_CRITICAL_SECONDS = 60  # >60s since last heartbeat - triggers CRITICAL
    
    def __init__(self):
        self.db_sync_success_count = 0
        self.db_sync_failure_count = 0
        self.db_sync_latency_ms = deque(maxlen=100)  # Rolling window (last 100 samples)
        self.leadership_changes = 0
        self.last_heartbeat_time: Optional[datetime] = None
        self._lock = threading.Lock()  # Thread-safe metrics updates
        self._leadership_change_times = deque(maxlen=100)  # Track timestamps of leadership changes
    
    def record_db_sync(self, success: bool, latency_ms: float):
        """
        Record database sync attempt with latency
        
        Args:
            success: Whether the sync operation succeeded
            latency_ms: Latency in milliseconds (float)
        
        Note:
            Latency is always recorded (even for failures) to track performance.
            The rolling window automatically maintains only the last 100 samples.
        """
        with self._lock:
            if success:
                self.db_sync_success_count += 1
            else:
                self.db_sync_failure_count += 1
            # Always record latency (even for failures) to track performance
            self.db_sync_latency_ms.append(latency_ms)
    
    def record_leadership_change(self):
        """Record a leadership transition"""
        with self._lock:
            self.leadership_changes += 1
            self._leadership_change_times.append(datetime.now())
    
    def update_heartbeat_time(self):
        """Update last heartbeat timestamp"""
        with self._lock:
            self.last_heartbeat_time = datetime.now()
    
    def _calculate_percentile(self, sorted_samples: list, percentile: float) -> float:
        """
        Calculate percentile value from sorted sample array
        
        Algorithm:
        1. Calculate index: (percentile / 100) * (n - 1)
        2. If index is integer, return sample at that index
        3. If index is fractional, interpolate between floor and ceiling indices
        
        Args:
            sorted_samples: Sorted list of latency samples (ascending)
            percentile: Percentile value (0-100), e.g., 95.0 for 95th percentile
        
        Returns:
            Percentile value in milliseconds
        """
        if not sorted_samples:
            return 0.0
        
        n = len(sorted_samples)
        if n == 1:
            return float(sorted_samples[0])
        
        # Calculate index: (percentile / 100) * (n - 1)
        index = (percentile / 100.0) * (n - 1)
        
        # Get floor and ceiling indices
        floor_idx = int(index)
        ceil_idx = min(floor_idx + 1, n - 1)
        
        # If index is integer, return sample at that index
        if floor_idx == ceil_idx:
            return float(sorted_samples[floor_idx])
        
        # Interpolate between floor and ceiling values
        weight = index - floor_idx
        return float(sorted_samples[floor_idx] * (1 - weight) + sorted_samples[ceil_idx] * weight)
    
    def get_stats(self) -> dict:
        """
        Get current metrics snapshot with comprehensive statistical analysis
        
        **Rolling Window Average Calculation:**
        The average latency is calculated as the arithmetic mean of all samples
        in the rolling window:
        
            avg_latency = sum(latency_samples) / len(latency_samples)
        
        This provides a simple moving average (SMA) over the last 100 samples.
        
        **Statistical Metrics:**
        - **Min/Max**: Direct min/max of samples in window
        - **Percentiles**: Calculated using sorted array and interpolation
          - p50 (median): Middle value, robust to outliers
          - p95: 95% of samples are below this (identifies slow operations)
          - p99: 99% of samples are below this (identifies extreme outliers)
        
        **Use Cases:**
        - **Average**: Overall performance trend
        - **p95/p99**: Alert thresholds (e.g., alert if p95 > 100ms)
        - **Min/Max**: Performance bounds
        
        Returns:
            Dictionary with comprehensive metrics:
            - db_sync_success: Count of successful syncs
            - db_sync_failure: Count of failed syncs
            - db_sync_total: Total sync attempts
            - db_sync_failure_rate: Failure rate (0.0-1.0)
            - db_sync_avg_latency_ms: Average latency (rolling window mean)
            - db_sync_min_latency_ms: Minimum latency in window
            - db_sync_max_latency_ms: Maximum latency in window
            - db_sync_p50_latency_ms: Median latency (50th percentile)
            - db_sync_p95_latency_ms: 95th percentile latency
            - db_sync_p99_latency_ms: 99th percentile latency
            - db_sync_latency_samples: Number of samples in rolling window
            - leadership_changes: Total leadership transitions
            - last_heartbeat: ISO timestamp of last heartbeat
        """
        with self._lock:
            total_syncs = self.db_sync_success_count + self.db_sync_failure_count
            latency_samples = list(self.db_sync_latency_ms)
            
            # Calculate basic statistics
            stats = {
                'db_sync_success': self.db_sync_success_count,
                'db_sync_failure': self.db_sync_failure_count,
                'db_sync_total': total_syncs,
                'db_sync_failure_rate': self.db_sync_failure_count / max(1, total_syncs),
                'db_sync_latency_samples': len(latency_samples),
                'leadership_changes': self.leadership_changes,
                'last_heartbeat': self.last_heartbeat_time.isoformat() if self.last_heartbeat_time else None
            }
            
            # Calculate latency statistics if we have samples
            if latency_samples:
                sorted_samples = sorted(latency_samples)
                
                # Average (arithmetic mean) - rolling window average
                stats['db_sync_avg_latency_ms'] = sum(latency_samples) / len(latency_samples)
                
                # Min/Max
                stats['db_sync_min_latency_ms'] = float(sorted_samples[0])
                stats['db_sync_max_latency_ms'] = float(sorted_samples[-1])
                
                # Percentiles (p50, p95, p99)
                stats['db_sync_p50_latency_ms'] = self._calculate_percentile(sorted_samples, 50.0)
                stats['db_sync_p95_latency_ms'] = self._calculate_percentile(sorted_samples, 95.0)
                stats['db_sync_p99_latency_ms'] = self._calculate_percentile(sorted_samples, 99.0)
            else:
                # No samples yet - return zeros
                stats['db_sync_avg_latency_ms'] = 0.0
                stats['db_sync_min_latency_ms'] = 0.0
                stats['db_sync_max_latency_ms'] = 0.0
                stats['db_sync_p50_latency_ms'] = 0.0
                stats['db_sync_p95_latency_ms'] = 0.0
                stats['db_sync_p99_latency_ms'] = 0.0
            
            return stats
    
    def check_alerts(self) -> dict:
        """
        Check metrics against alert thresholds and return alert status
        
        Evaluates three critical metrics:
        1. DB sync failure rate
        2. Leadership change frequency (flapping detection)
        3. Heartbeat staleness
        
        Returns:
            Dictionary with alert status for each metric:
            {
                'db_sync_failure_rate': {
                    'status': 'OK' | 'WARNING' | 'CRITICAL',
                    'value': float,  # Current failure rate
                    'threshold_warning': float,  # Warning threshold
                    'threshold_critical': float,  # Critical threshold
                    'message': str  # Human-readable alert message
                },
                'leadership_changes': {
                    'status': 'OK' | 'WARNING' | 'CRITICAL',
                    'value': float,  # Changes per hour
                    'threshold_warning': float,
                    'threshold_critical': float,
                    'message': str
                },
                'heartbeat_staleness': {
                    'status': 'OK' | 'WARNING' | 'CRITICAL',
                    'value': float,  # Seconds since last heartbeat
                    'threshold_warning': float,
                    'threshold_critical': float,
                    'message': str
                },
                'overall_status': 'OK' | 'WARNING' | 'CRITICAL'  # Worst status
            }
        """
        with self._lock:
            alerts = {}
            overall_status = 'OK'
            
            # 1. Check DB sync failure rate
            total_syncs = self.db_sync_success_count + self.db_sync_failure_count
            failure_rate = self.db_sync_failure_count / max(1, total_syncs)
            
            if failure_rate >= self.DB_SYNC_FAILURE_RATE_CRITICAL:
                status = 'CRITICAL'
                message = f"DB sync failure rate is {failure_rate*100:.1f}% (CRITICAL threshold: {self.DB_SYNC_FAILURE_RATE_CRITICAL*100:.1f}%)"
            elif failure_rate >= self.DB_SYNC_FAILURE_RATE_WARNING:
                status = 'WARNING'
                message = f"DB sync failure rate is {failure_rate*100:.1f}% (WARNING threshold: {self.DB_SYNC_FAILURE_RATE_WARNING*100:.1f}%)"
            else:
                status = 'OK'
                message = f"DB sync failure rate is {failure_rate*100:.1f}% (within normal range)"
            
            alerts['db_sync_failure_rate'] = {
                'status': status,
                'value': failure_rate,
                'threshold_warning': self.DB_SYNC_FAILURE_RATE_WARNING,
                'threshold_critical': self.DB_SYNC_FAILURE_RATE_CRITICAL,
                'message': message
            }
            
            # Update overall status
            if status == 'CRITICAL':
                overall_status = 'CRITICAL'
            elif status == 'WARNING' and overall_status == 'OK':
                overall_status = 'WARNING'
            
            # 2. Check leadership change frequency (flapping detection)
            # Count changes in the last hour
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            
            recent_changes = [ts for ts in self._leadership_change_times if ts >= one_hour_ago]
            changes_per_hour = len(recent_changes)
            
            if changes_per_hour >= self.LEADERSHIP_CHANGES_CRITICAL_PER_HOUR:
                status = 'CRITICAL'
                message = f"Leadership changed {changes_per_hour} times in the last hour (CRITICAL threshold: {self.LEADERSHIP_CHANGES_CRITICAL_PER_HOUR}/hour)"
            elif changes_per_hour >= self.LEADERSHIP_CHANGES_WARNING_PER_HOUR:
                status = 'WARNING'
                message = f"Leadership changed {changes_per_hour} times in the last hour (WARNING threshold: {self.LEADERSHIP_CHANGES_WARNING_PER_HOUR}/hour)"
            else:
                status = 'OK'
                message = f"Leadership changed {changes_per_hour} times in the last hour (within normal range)"
            
            alerts['leadership_changes'] = {
                'status': status,
                'value': changes_per_hour,
                'threshold_warning': self.LEADERSHIP_CHANGES_WARNING_PER_HOUR,
                'threshold_critical': self.LEADERSHIP_CHANGES_CRITICAL_PER_HOUR,
                'message': message
            }
            
            # Update overall status
            if status == 'CRITICAL':
                overall_status = 'CRITICAL'
            elif status == 'WARNING' and overall_status == 'OK':
                overall_status = 'WARNING'
            
            # 3. Check heartbeat staleness
            if self.last_heartbeat_time is None:
                status = 'CRITICAL'
                seconds_since_heartbeat = float('inf')
                message = "No heartbeat recorded (instance may not be running)"
            else:
                seconds_since_heartbeat = (now - self.last_heartbeat_time).total_seconds()
                
                if seconds_since_heartbeat >= self.HEARTBEAT_STALE_CRITICAL_SECONDS:
                    status = 'CRITICAL'
                    message = f"No heartbeat for {seconds_since_heartbeat:.1f} seconds (CRITICAL threshold: {self.HEARTBEAT_STALE_CRITICAL_SECONDS}s)"
                elif seconds_since_heartbeat >= self.HEARTBEAT_STALE_WARNING_SECONDS:
                    status = 'WARNING'
                    message = f"No heartbeat for {seconds_since_heartbeat:.1f} seconds (WARNING threshold: {self.HEARTBEAT_STALE_WARNING_SECONDS}s)"
                else:
                    status = 'OK'
                    message = f"Last heartbeat {seconds_since_heartbeat:.1f} seconds ago (within normal range)"
            
            alerts['heartbeat_staleness'] = {
                'status': status,
                'value': seconds_since_heartbeat if self.last_heartbeat_time else None,
                'threshold_warning': self.HEARTBEAT_STALE_WARNING_SECONDS,
                'threshold_critical': self.HEARTBEAT_STALE_CRITICAL_SECONDS,
                'message': message
            }
            
            # Update overall status
            if status == 'CRITICAL':
                overall_status = 'CRITICAL'
            elif status == 'WARNING' and overall_status == 'OK':
                overall_status = 'WARNING'
            
            alerts['overall_status'] = overall_status
            return alerts


class RedisCoordinator:
    """Redis-based distributed coordination with connection pooling and resilience"""
    
    # Redis key prefixes (for future use in leader election, heartbeat, locking)
    LEADER_KEY = "pm:leader"
    HEARTBEAT_PREFIX = "pm:heartbeat:"
    SIGNAL_LOCK_PREFIX = "pm:signal_lock:"
    
    # TTL values (seconds) - defined here for future use
    LEADER_TTL = 10  # Leader key expires in 10 seconds
    HEARTBEAT_TTL = 30  # Heartbeat expires in 30 seconds
    SIGNAL_LOCK_TTL = 30  # Signal lock expires in 30 seconds
    
    # Heartbeat interval configuration
    RENEWAL_INTERVAL_RATIO = 0.5  # Renew at TTL/2 (e.g., 5s for 10s TTL)
    ELECTION_INTERVAL = 2.5  # Seconds between election attempts when not leader
    
    def __init__(self, redis_config: dict, fallback_mode: bool = False, db_manager=None):
        """
        Initialize Redis coordinator with connection pooling
        
        Args:
            redis_config: {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'password': None,
                'ssl': False,
                'socket_timeout': 2.0,
                'enable_redis': True
            }
            fallback_mode: If True, operate in DB-only mode (no Redis)
            db_manager: Optional DatabaseStateManager for syncing leader status to PostgreSQL
        """
        self.fallback_mode = fallback_mode
        self.redis_client = None
        self.connection_pool = None
        self.instance_id = self._load_or_create_instance_id()
        self.db_manager = db_manager  # For syncing to PostgreSQL
        
        # Thread-safe leadership state
        self._is_leader = False
        self._is_leader_lock = threading.Lock()
        self._last_leader_state = False  # Track previous state for change detection
        
        # Heartbeat thread management
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop_event = threading.Event()
        self._heartbeat_iteration = 0  # Counter for periodic split-brain checks
        
        # Metrics tracking
        self.metrics = CoordinatorMetrics()
        
        if fallback_mode:
            logger.warning("Redis fallback mode enabled - using database-only coordination")
            return
        
        # Check if Redis is enabled
        if not redis_config.get('enable_redis', True):
            logger.warning("Redis disabled in config - enabling fallback mode")
            self.fallback_mode = True
            return
        
        try:
            # Create connection pool with direct parameters
            # Note: SSL is handled via connection_class if needed, but for now we skip it
            pool_kwargs = {
                'host': redis_config.get('host', 'localhost'),
                'port': redis_config.get('port', 6379),
                'db': redis_config.get('db', 0),
                'password': redis_config.get('password'),
                'socket_timeout': redis_config.get('socket_timeout', 2.0),
                'socket_connect_timeout': redis_config.get('socket_timeout', 2.0),
                'decode_responses': True,
                'max_connections': redis_config.get('max_connections', 50)
            }
            
            # Only add SSL if explicitly True (skip for now to avoid connection issues)
            # SSL support can be added later if needed for production
            
            self.connection_pool = ConnectionPool(**pool_kwargs)
            
            # Create Redis client using the connection pool
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            
            # Test connection with ping (without retry decorator to avoid delays during init)
            try:
                result = self.redis_client.ping()
                if not result:
                    raise redis.ConnectionError("Ping returned False")
            except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
                logger.error(f"Redis ping failed on initialization: {e}")
                logger.warning("Enabling fallback mode - Redis unavailable")
                
                # Cleanup connection pool before abandoning it
                if self.connection_pool:
                    try:
                        if self.redis_client:
                            self.redis_client.close()
                    except Exception:
                        pass  # Best effort cleanup
                
                self.fallback_mode = True
                self.redis_client = None
                self.connection_pool = None
                return
            
            logger.info(f"Redis coordinator initialized: instance={self.instance_id}")
            
            # Initialize instance metadata in database if available
            if self.db_manager:
                self._sync_leader_status_to_db()
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Redis connection failed on initialization: {e}")
            logger.warning("Enabling fallback mode - Redis unavailable")
            
            # Cleanup connection pool before abandoning it
            if self.connection_pool:
                try:
                    if self.redis_client:
                        self.redis_client.close()
                except Exception:
                    pass  # Best effort cleanup
            
            self.fallback_mode = True
            self.redis_client = None
            self.connection_pool = None
        except Exception as e:
            logger.error(f"Unexpected error initializing Redis: {e}")
            
            # Cleanup connection pool before abandoning it
            if self.connection_pool:
                try:
                    if self.redis_client:
                        self.redis_client.close()
                except Exception:
                    pass  # Best effort cleanup
            
            self.fallback_mode = True
            self.redis_client = None
            self.connection_pool = None
    
    def _load_or_create_instance_id(self) -> str:
        """
        Load persisted instance ID or create new one with UUID-PID format
        
        Returns:
            Instance ID string in format "uuid-pid" for concurrent instance support
        """
        instance_id_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            '.redis_instance_id'
        )
        
        current_pid = os.getpid()
        
        if os.path.exists(instance_id_file):
            try:
                with open(instance_id_file, 'r') as f:
                    persisted_id = f.read().strip()
                    if persisted_id:
                        # Extract UUID part using dash counting
                        # UUID format: 4 dashes (e.g., "550e8400-e29b-41d4-a716-446655440000")
                        # UUID-PID format: 5 dashes (e.g., "550e8400-e29b-41d4-a716-446655440000-12345")
                        dash_count = persisted_id.count('-')
                        
                        if dash_count == 5:
                            # UUID-PID format (4 dashes in UUID + 1 before PID)
                            uuid_part = persisted_id.rsplit('-', 1)[0]
                        elif dash_count == 4:
                            # Plain UUID format (standard UUID with 4 dashes)
                            uuid_part = persisted_id
                        else:
                            # Malformed or unexpected format - use as-is with warning
                            logger.warning(
                                f"Unexpected instance ID format (dash_count={dash_count}): {persisted_id}. "
                                f"Using as-is."
                            )
                            uuid_part = persisted_id
                        
                        # Always append current PID for concurrent instance support
                        instance_id = f"{uuid_part}-{current_pid}"
                        logger.info(f"Loaded persisted instance ID (UUID-PID): {instance_id}")
                        return instance_id
            except Exception as e:
                logger.warning(f"Failed to load instance ID: {e}")
        
        # Create new instance ID with UUID-PID format
        uuid_part = str(uuid.uuid4())
        instance_id = f"{uuid_part}-{current_pid}"
        try:
            with open(instance_id_file, 'w') as f:
                # Store only UUID part (without PID) for persistence
                f.write(uuid_part)
            logger.info(f"Created new instance ID (UUID-PID): {instance_id}")
        except Exception as e:
            logger.warning(f"Failed to persist instance ID: {e}")
        
        return instance_id
    
    def _get_connection(self) -> Optional[redis.Redis]:
        """
        Get Redis connection from pool with retry logic
        
        Returns:
            Redis client instance, or None if in fallback mode or connection failed
        """
        if self.fallback_mode:
            return None
        
        if self.redis_client is None:
            logger.error("Redis client not initialized")
            return None
        
        # Connection is managed by the pool, just return the client
        # The pool handles connection lifecycle automatically
        return self.redis_client
    
    def ping(self) -> bool:
        """
        Verify Redis connectivity with retry logic
        
        Returns:
            True if Redis is reachable, False otherwise
        """
        if self.fallback_mode:
            return False
        
        if self.redis_client is None:
            return False
        
        # Use retry logic for connection errors
        last_exception = None
        max_retries = 3
        base_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                result = self.redis_client.ping()
                return bool(result)
            except (redis.ConnectionError, redis.TimeoutError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Redis ping failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.warning(f"Redis ping failed after {max_retries} attempts: {e}")
            except redis.RedisError as e:
                # Other Redis errors (not connection-related) - don't retry
                logger.error(f"Redis error during ping: {e}")
                return False
        
        # All retries exhausted
        return False
    
    def _get_hostname_safe(self) -> str:
        """
        Get hostname safely, handling errors gracefully
        
        Returns:
            Hostname string, or 'unknown' if retrieval fails
        """
        try:
            return socket.gethostname()
        except Exception:
            return 'unknown'
    
    def is_available(self) -> bool:
        """
        Check if Redis is available (not in fallback mode)
        
        Returns:
            True if Redis is available, False if in fallback mode
        """
        return not self.fallback_mode and self.redis_client is not None
    
    @property
    def is_leader(self) -> bool:
        """
        Thread-safe property to check if this instance is the leader
        
        Returns:
            True if this instance is the leader, False otherwise
        """
        with self._is_leader_lock:
            return self._is_leader
    
    @is_leader.setter
    def is_leader(self, value: bool):
        """
        Thread-safe setter for leader status
        
        Also syncs to PostgreSQL if db_manager is available and state changed.
        
        Args:
            value: New leader status
        """
        with self._is_leader_lock:
            old_value = self._is_leader
            self._is_leader = value
            
            # Sync to database if state changed
            if old_value != value:
                # Record leadership change in metrics
                self.metrics.record_leadership_change()
                self._sync_leader_status_to_db()
                # Record in leadership history for audit trail
                if self.db_manager:
                    reason = 'election' if value else 'graceful_shutdown'  # Default reasons
                    self.db_manager.record_leadership_transition(
                        self.instance_id, value, reason, self._get_hostname_safe()
                    )
    
    def _sync_leader_status_to_db(self):
        """
        Sync current leader status to PostgreSQL instance_metadata table
        
        This is called automatically when leadership state changes.
        Also updates last_heartbeat timestamp.
        Records metrics for monitoring.
        """
        if not self.db_manager:
            return  # No database manager available
        
        start_time = time.time()
        success = False
        try:
            # Get hostname for metadata
            hostname = self._get_hostname_safe()
            
            # Sync to database
            self.db_manager.upsert_instance_metadata(
                instance_id=self.instance_id,
                is_leader=self._is_leader,
                status='active',
                hostname=hostname
            )
            success = True
            logger.debug(f"[{self.instance_id}] Leader status synced to database: is_leader={self._is_leader}")
        except Exception as e:
            logger.warning(f"[{self.instance_id}] Failed to sync leader status to database: {e}")
        finally:
            # Record metrics with latency
            latency_ms = (time.time() - start_time) * 1000
            self.metrics.record_db_sync(success, latency_ms)
    
    def _update_heartbeat_in_db(self):
        """
        Update last_heartbeat timestamp in PostgreSQL instance_metadata table
        
        Called periodically from heartbeat loop to keep database updated.
        Records metrics for monitoring.
        """
        if not self.db_manager:
            return  # No database manager available
        
        start_time = time.time()
        success = False
        try:
            hostname = self._get_hostname_safe()
            self.db_manager.upsert_instance_metadata(
                instance_id=self.instance_id,
                is_leader=self._is_leader,
                status='active',
                hostname=hostname
            )
            success = True
        except Exception as e:
            logger.debug(f"[{self.instance_id}] Failed to update heartbeat in database: {e}")
        finally:
            # Record metrics with latency
            latency_ms = (time.time() - start_time) * 1000
            self.metrics.record_db_sync(success, latency_ms)
            # Update heartbeat timestamp in metrics
            self.metrics.update_heartbeat_time()
    
    # ===== LEADER ELECTION =====
    
    def elect_leader(self) -> bool:
        """
        Attempt to become leader using atomic SETNX with TTL
        
        Uses Redis SET with NX (only if not exists) and EX (expiration) for atomic
        leader election. Only one instance can acquire the leader key at a time.
        
        Includes re-entrancy check: if we're already the leader (value matches our
        instance_id), extend TTL to prevent expiration.
        
        Returns:
            True if this instance became leader or is already leader, False otherwise
        """
        if self.fallback_mode or self.redis_client is None:
            return False
        
        try:
            # Try to set leader key with our instance ID
            # SET key value NX EX seconds - atomic SETNX with expiration
            acquired = self.redis_client.set(
                self.LEADER_KEY,
                self.instance_id,
                nx=True,  # Only set if not exists (SETNX)
                ex=self.LEADER_TTL  # Expire after TTL seconds
            )
            
            if acquired:
                self.is_leader = True
                logger.error(f"🚨 [{self.instance_id}] BECAME LEADER - Now processing signals")
                return True
            
            # Re-entrancy check: if we're already the leader locally, use atomic renewal
            # This handles the case where we're already leader but TTL is about to expire
            # Only check if we're already marked as leader locally
            # This handles re-entrancy (accidental double-calls) and extends TTL if needed
            # Uses atomic renew_leadership() to prevent race conditions
            if self.is_leader:
                if self.renew_leadership():
                    logger.debug(f"[{self.instance_id}] Already leader - renewed TTL")
                    return True
            
            return False
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection error in leader election: {e}")
            return False
        except redis.RedisError as e:
            logger.error(f"Redis error in leader election: {e}")
            return False
    
    def try_become_leader(self) -> bool:
        """
        Attempt to become leader using atomic SETNX with TTL
        
        Alias for elect_leader() for backward compatibility.
        Uses Redis SET with NX (only if not exists) and EX (expiration) for atomic
        leader election. Only one instance can acquire the leader key at a time.
        
        Returns:
            True if this instance became leader, False otherwise
        """
        return self.elect_leader()
    
    def renew_leadership(self) -> bool:
        """
        Renew leader key if we are the current leader
        
        Uses Lua script for atomic get-and-set operation to ensure we only renew
        if we're still the leader. This prevents race conditions where leadership
        might have changed between checking and renewing.
        
        Returns:
            True if renewal successful, False if lost leadership or error
        """
        if self.fallback_mode or self.redis_client is None:
            return False
        
        if not self.is_leader:
            return False
        
        try:
            # Lua script for atomic renewal: only renew if we're still the leader
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """
            
            renewed = self.redis_client.eval(
                lua_script,
                1,  # Number of keys
                self.LEADER_KEY,  # KEYS[1]
                self.instance_id,  # ARGV[1] - our instance ID
                self.LEADER_TTL  # ARGV[2] - TTL in seconds
            )
            
            # Lua script returns 1 (truthy) on success, 0 (falsy) on failure
            # Check explicitly for 1 or True to handle edge cases
            if renewed == 1 or renewed is True:
                return True
            else:
                self.is_leader = False
                logger.critical(f"🚨 [{self.instance_id}] LOST LEADERSHIP - Stopped processing signals")
                return False
                
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection error renewing leadership: {e}")
            self.is_leader = False
            return False
        except redis.RedisError as e:
            logger.error(f"Redis error renewing leadership: {e}")
            self.is_leader = False
            return False
    
    def get_current_leader(self) -> Optional[str]:
        """
        Get current leader instance ID
        
        Returns:
            Instance ID of current leader, or None if no leader or error
        """
        if self.fallback_mode or self.redis_client is None:
            return None
        
        try:
            leader_id = self.redis_client.get(self.LEADER_KEY)
            if leader_id:
                return leader_id
            return None
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection error getting leader: {e}")
            return None
        except redis.RedisError as e:
            logger.error(f"Redis error getting leader: {e}")
            return None
    
    def detect_split_brain(self) -> Optional[dict]:
        """
        Detect split-brain scenario: Redis leader != Database leader
        
        Returns dict with conflict details if detected, None otherwise.
        Format: {
            'redis_leader': instance_id or None,
            'db_leader': instance_id or None,
            'conflict': True/False
        }
        
        Critical for trading systems: split-brain = 2 instances process same signal
        = DOUBLE POSITION SIZE = FINANCIAL DISASTER
        """
        if not self.db_manager:
            # No DB manager - cannot detect split-brain
            return None
        
        try:
            # Get leader from Redis
            redis_leader = self.get_current_leader()
            
            # CRITICAL: Use force_fresh=True to ensure we see latest commits
            # This prevents false split-brain detection due to stale reads
            # Without this, connection pool isolation can cause us to see stale data
            db_leader_info = self.db_manager.get_current_leader_from_db(force_fresh=True)
            db_leader = db_leader_info['instance_id'] if db_leader_info else None
            
            # Check for conflict
            conflict = False
            if redis_leader and db_leader:
                # Both have leaders - check if they match
                conflict = (redis_leader != db_leader)
            elif redis_leader and not db_leader:
                # Redis has leader but DB doesn't (possible if DB sync failed)
                conflict = True
            elif not redis_leader and db_leader:
                # DB has leader but Redis doesn't (possible if Redis key expired)
                conflict = True
            # else: both None - no conflict
            
            if conflict:
                return {
                    'redis_leader': redis_leader,
                    'db_leader': db_leader,
                    'conflict': True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting split-brain: {e}", exc_info=True)
            return None
    
    def release_leadership(self) -> bool:
        """
        Release leadership if we are the current leader
        
        Uses Lua script to atomically delete the leader key only if we're still
        the leader. This prevents accidentally releasing leadership if we've already
        lost it.
        
        Returns:
            True if leadership was released, False otherwise
        """
        if self.fallback_mode or self.redis_client is None:
            return False
        
        if not self.is_leader:
            return False
        
        try:
            # Lua script for atomic release: only delete if we're still the leader
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            released = self.redis_client.eval(
                lua_script,
                1,  # Number of keys
                self.LEADER_KEY,  # KEYS[1]
                self.instance_id  # ARGV[1] - our instance ID
            )
            
            # Lua script returns 1 (truthy) on success, 0 (falsy) on failure
            if released == 1 or released is True:
                self.is_leader = False
                logger.error(f"🚨 [{self.instance_id}] Released leadership gracefully")
                return True
            else:
                # We're not the leader anymore
                self.is_leader = False
                return False
                
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection error releasing leadership: {e}")
            self.is_leader = False
            return False
        except redis.RedisError as e:
            logger.error(f"Redis error releasing leadership: {e}")
            self.is_leader = False
            return False
    
    # ===== HEARTBEAT MECHANISM =====
    
    def start_heartbeat(self) -> bool:
        """
        Start background heartbeat thread for leadership management
        
        The heartbeat thread will:
        - If currently leader: Renew leadership every TTL/2 seconds (5s for 10s TTL)
        - If not leader: Attempt to acquire leadership every 2-3 seconds
        
        Returns:
            True if heartbeat started successfully, False otherwise
        """
        if self.fallback_mode:
            logger.debug("Heartbeat not started - in fallback mode")
            return False
        
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            logger.warning("Heartbeat already running")
            return False
        
        # Reset stop event and start new thread
        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"RedisCoordinator-Heartbeat-{self.instance_id}",
            daemon=True
        )
        self._heartbeat_thread.start()
        logger.info(f"[{self.instance_id}] Heartbeat thread started")
        return True
    
    def _heartbeat_loop(self):
        """
        Background loop for heartbeat mechanism
        
        This method runs in a separate thread and manages leadership lifecycle:
        - Renews leadership if currently leader (every TTL/2 seconds)
        - Attempts to acquire leadership if not leader (every 2-3 seconds)
        """
        renewal_interval = self.LEADER_TTL * self.RENEWAL_INTERVAL_RATIO
        election_interval = self.ELECTION_INTERVAL
        
        logger.info(f"[{self.instance_id}] Heartbeat loop started (renewal: {renewal_interval}s, election: {election_interval}s)")
        
        while not self._heartbeat_stop_event.is_set():
            try:
                # Increment heartbeat iteration counter
                self._heartbeat_iteration += 1
                
                # Update heartbeat in database periodically
                self._update_heartbeat_in_db()
                
                # Periodic split-brain detection (every 10 iterations = ~50 seconds)
                # This prevents excessive DB queries while ensuring timely detection
                if self._heartbeat_iteration % 10 == 0:
                    conflict = self.detect_split_brain()
                    if conflict and conflict.get('conflict'):
                        logger.error(
                            f"🚨 SPLIT-BRAIN DETECTED: Redis={conflict.get('redis_leader')}, "
                            f"DB={conflict.get('db_leader')}"
                        )
                        
                        # If database says someone else is leader, self-demote immediately
                        # This prevents duplicate signal processing (CRITICAL for trading)
                        if conflict.get('db_leader') and conflict.get('db_leader') != self.instance_id:
                            logger.critical(
                                f"🚨 [{self.instance_id}] Self-demoting due to split-brain. "
                                f"DB reports {conflict.get('db_leader')} as leader"
                            )
                            # Release Redis lock first (this will set is_leader = False internally)
                            self.release_leadership()
                            # Ensure state is correct (release_leadership sets it, but be explicit)
                            self.is_leader = False
                
                if self.is_leader:
                    # We're the leader - renew the lease
                    if not self.renew_leadership():
                        # Lost leadership - will attempt to reacquire on next iteration
                        logger.debug(f"[{self.instance_id}] Will retry leadership acquisition on next cycle")
                    
                    # Wait for renewal interval or stop event
                    if self._heartbeat_stop_event.wait(timeout=renewal_interval):
                        break  # Stop event was set
                else:
                    # Not the leader - try to acquire leadership
                    if self.try_become_leader():
                        logger.error(f"🚨 [{self.instance_id}] Acquired leadership via heartbeat - Now processing signals")
                    
                    # Wait for election interval or stop event
                    if self._heartbeat_stop_event.wait(timeout=election_interval):
                        break  # Stop event was set
                        
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"[{self.instance_id}] Redis connection error in heartbeat: {e}")
                # Wait a bit before retrying to avoid tight loop
                if self._heartbeat_stop_event.wait(timeout=1.0):
                    break
            except redis.RedisError as e:
                logger.error(f"[{self.instance_id}] Redis error in heartbeat: {e}")
                # Wait a bit before retrying
                if self._heartbeat_stop_event.wait(timeout=1.0):
                    break
            except Exception as e:
                logger.error(f"[{self.instance_id}] Unexpected error in heartbeat loop: {e}", exc_info=True)
                # Wait a bit before retrying
                if self._heartbeat_stop_event.wait(timeout=1.0):
                    break
        
        logger.info(f"[{self.instance_id}] Heartbeat loop stopped")
    
    def stop_heartbeat(self, timeout: float = 5.0) -> bool:
        """
        Stop the heartbeat thread gracefully
        
        Args:
            timeout: Maximum time to wait for thread to stop (seconds)
            
        Returns:
            True if heartbeat stopped successfully, False otherwise
        """
        if self._heartbeat_thread is None or not self._heartbeat_thread.is_alive():
            return True
        
        logger.info(f"[{self.instance_id}] Stopping heartbeat thread...")
        
        # Signal thread to stop
        self._heartbeat_stop_event.set()
        
        # Release leadership if we're the leader
        if self.is_leader:
            self.release_leadership()
        
        # Wait for thread to finish
        self._heartbeat_thread.join(timeout=timeout)
        
        if self._heartbeat_thread.is_alive():
            logger.warning(f"[{self.instance_id}] Heartbeat thread did not stop within {timeout}s")
            return False
        
        self._heartbeat_thread = None
        logger.info(f"[{self.instance_id}] Heartbeat thread stopped")
        return True
    
    def is_heartbeat_running(self) -> bool:
        """
        Check if heartbeat thread is currently running
        
        Returns:
            True if heartbeat thread exists and is alive, False otherwise
        """
        return (self._heartbeat_thread is not None and
                self._heartbeat_thread.is_alive())
    
    def get_metrics(self) -> dict:
        """
        Get current coordinator metrics for monitoring
        
        Returns comprehensive metrics including:
        - DB sync health (success/failure counts, failure rate, latency)
        - Leadership changes count
        - Last heartbeat timestamp
        - Current leader status (Redis and DB)
        - Instance information
        - Alert status (OK/WARNING/CRITICAL)
        
        Returns:
            Dictionary with all metrics for monitoring/alerting, including:
            - All metrics from metrics.get_stats()
            - alerts: Dictionary with alert status for each metric
            - overall_alert_status: 'OK' | 'WARNING' | 'CRITICAL'
        """
        stats = self.metrics.get_stats()
        
        # Get alert status
        alerts = self.metrics.check_alerts()
        
        # Add current leader information
        redis_leader = self.get_current_leader()
        db_leader_info = None
        if self.db_manager:
            db_leader_info = self.db_manager.get_current_leader_from_db()
        
        stats.update({
            'current_leader_redis': redis_leader,
            'current_leader_db': db_leader_info['instance_id'] if db_leader_info else None,
            'this_instance': self.instance_id,
            'is_leader': self.is_leader,
            'heartbeat_running': self.is_heartbeat_running(),
            'fallback_mode': self.fallback_mode,
            'alerts': alerts,  # Include alert status
            'overall_alert_status': alerts.get('overall_status', 'OK')
        })
        
        return stats
    
    def close(self):
        """Close Redis connection pool and stop heartbeat"""
        # Stop heartbeat first
        self.stop_heartbeat()
        
        # Close connection pool
        if self.connection_pool:
            try:
                self.connection_pool.disconnect()
                logger.info("Redis connection pool closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection pool: {e}")
            finally:
                self.connection_pool = None
                self.redis_client = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup"""
        self.close()

