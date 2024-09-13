from fastapi import HTTPException, Request, FastAPI
from collections import defaultdict, deque
from fastapi.responses import JSONResponse
from typing import Dict, List, Callable
from dataclasses import dataclass
import time as time_module
import asyncio

# Define a dataclass to store request statistics
@dataclass
class RequestStats:
    allowed: int = 0
    denied: int = 0
    last_allowed: float = 0
    last_denied: float = 0

# Define a RateLimiter class to handle rate limiting
class RateLimiter:
    def __init__(self, rate: int, capacity: int = 1024, burst: int = None, stats_window: int = 60, enable_stats: bool = True, seconds: int = 0, minutes: int = 0, hours: int = 0):
        """
        Initializes a RateLimiter instance.

        Args:
            rate (int): The rate at which tokens are added.
            capacity (int): Maximum number of tokens that can be stored.
            burst (int, optional): Extra tokens allowed during bursts. Defaults to 0 if not provided.
            stats_window (int, optional): Time window for collecting stats. Defaults to 60 seconds.
            enable_stats (bool, optional): Enables request statistics collection. Defaults to True.
            seconds (int, at least one of seconds, minutes, or hours must be provided): Number of seconds.
            minutes (int, at least one of seconds, minutes, or hours must be provided): Number of minutes.
            hours (int, at least one of seconds, minutes, or hours must be provided): Number of hours.
        """
        
        # Calculate total time in seconds from hours, minutes, and seconds
        self.time = (seconds) + (minutes * 60) + (hours * 3600)
        
        # Validate that the total time is greater than zero
        if self.time <= 0:
            raise ValueError("The total time must be greater than zero.")
        # Validate the rate
        if rate <= 0:
            raise ValueError("The rate must be greater than zero.")
        # Validate the capacity
        if capacity <= 0:
            raise ValueError("The capacity must be greater than zero.")
        # Validate the burst
        if burst is not None and burst < 0:
            raise ValueError("The burst must be greater than or equal to zero.")
        # Validate the stats window
        if stats_window <= 0:
            raise ValueError("The stats window must be greater than zero.")
                
        # Initialize rate, capacity
        self.rate = rate
        self.capacity = capacity
        
        # Initialize burst if provided, otherwise default to 0
        self.burst = burst if burst is not None else 0
        
        # Initialize stats window and stats tracking
        self.stats_window = stats_window
        self.enable_stats = enable_stats

        # Initialize token buckets and last refill timestamps for each client/request key
        self.tokens: Dict[str, float] = defaultdict(lambda: self.capacity + self.burst)
        self.last_refill_timestamp: Dict[str, float] = defaultdict(time_module.time)

        # Initialize statistics if enabled
        self.stats: Dict[str, RequestStats] = defaultdict(RequestStats)
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=stats_window))

        # List of callbacks to execute after each request is processed
        self.callbacks: List[Callable] = []

    # Method to allow a request based on rate limiting
    async def allow_request(self, key: str) -> bool:
        # If rate is zero, no tokens are available, so immediately raise an HTTPException
        if self.rate == 0:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. No tokens available due to zero rate."
            )

        # Get the current time
        now = time_module.time()

        # If the key is not in the token bucket, initialize it with the maximum capacity plus burst tokens
        if key not in self.tokens:
            self.tokens[key] = self.capacity + self.burst
            self.last_refill_timestamp[key] = now

        # Calculate the elapsed time since the last refill of tokens
        elapsed_time = max(0, now - self.last_refill_timestamp[key])

        # Calculate how many tokens to add based on the elapsed time and rate
        tokens_to_add = elapsed_time * (self.rate / self.time)

        # Update the current tokens, making sure it does not exceed the maximum (capacity + burst)
        current_tokens = min(self.capacity + self.burst, self.tokens[key] + tokens_to_add)

        # If there is at least 1 token, allow the request and decrement the token count
        if current_tokens >= 1:
            self.tokens[key] = current_tokens - 1
            self.last_refill_timestamp[key] = now
            request_allowed = True
        else:
            # If no tokens are available, disallow the request
            request_allowed = False

        # Update stats for the request, even if the request is denied
        self.update_stats(key, request_allowed, now)

        # Trigger any associated callbacks asynchronously
        await self.trigger_callbacks(request_allowed, key)

        # If the request is not allowed, calculate the wait time before the next token is available
        if not request_allowed:
            wait_time = (1 - current_tokens) / (self.rate / self.time)
            # Raise an HTTP exception to indicate that the rate limit has been exceeded
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {wait_time:.2f} seconds."
            )

        # Return whether the request was allowed
        return request_allowed

    # Method to calculate the wait time before the next token is available for the given key
    async def get_wait_time(self, key: str) -> float:
        # Get the current time
        now = time_module.time()

        # If the key doesn't exist in the token bucket, there's no wait time
        if key not in self.tokens:
            return 0

        # Calculate the elapsed time since the last refill
        elapsed_time = max(0, now - self.last_refill_timestamp[key])

        # Calculate how many tokens to add based on the elapsed time and rate
        tokens_to_add = elapsed_time * (self.rate / self.time)

        # Update the current tokens, making sure it doesn't exceed the maximum
        current_tokens = min(self.capacity + self.burst, self.tokens[key] + tokens_to_add)

        # If at least 1 token is available, there's no wait time
        if current_tokens >= 1:
            return 0

        # Calculate the additional tokens required and the time to refill those tokens
        tokens_needed = 1 - current_tokens
        wait_time = tokens_needed / (self.rate / self.time)

        # Return the calculated wait time
        return wait_time

    # Method to update statistics for a specific key based on whether a request was allowed or denied
    def update_stats(self, key: str, allowed: bool, timestamp: float):
        # Only update stats if stats collection is enabled
        if self.enable_stats:
            # Retrieve the statistics object for the given key
            stats = self.stats[key]
            
            # If the request was allowed, increment the allowed count and update the last allowed timestamp
            if allowed:
                stats.allowed += 1
                stats.last_allowed = timestamp
            else:
                # If the request was denied, increment the denied count and update the last denied timestamp
                stats.denied += 1
                stats.last_denied = timestamp

            # Record the request history by appending the (timestamp, allowed) tuple to the request history list
            self.request_history[key].append((timestamp, allowed))

    # Implement the get_stats method
    def get_stats(self, key: str) -> Dict:
        # Return an error if stats collection is disabled
        if not self.enable_stats:
            return {"error": "Stats collection is disabled"}

        # Retrieve the stats for the given key
        stats = self.stats[key]
        now = time_module.time()

        # Calculate the start of the stats window
        window_start = now - self.stats_window

        # Filter requests that occurred within the stats window
        window_requests = [request for request in self.request_history[key] if request[0] >= window_start]

        # Count allowed and denied requests in the current window
        window_allowed = sum(1 for request in window_requests if request[1])
        window_denied = len(window_requests) - window_allowed

        # Return the statistics, including total and window-specific data
        return {
            "total_allowed": stats.allowed,
            "total_denied": stats.denied,
            "window_allowed": window_allowed,
            "window_denied": window_denied,
            "current_tokens": self.tokens[key],
            "current_capacity": self.capacity,
            "time_since_last_allowed": now - stats.last_allowed if stats.last_allowed else None,
            "time_since_last_denied": now - stats.last_denied if stats.last_denied else None,
        }

    # Method to reset the state of the rate limiter for a specific key or for all keys
    def reset(self, key: str = None):
        # Get the current time
        now = time_module.time()

        # If a key is provided and it doesn't exist in the token bucket, return without doing anything
        if key:
            # If a specific key is provided, reset tokens and refill timestamp for that key
            self.tokens[key] = self.capacity + self.burst
            self.last_refill_timestamp[key] = now

            # If stats tracking is enabled, reset the stats and clear the request history for the key
            if self.enable_stats:
                self.stats[key] = RequestStats()
                self.request_history[key].clear()
        else:
            # If no key is provided, clear all tokens and refill timestamps for all keys
            self.tokens.clear()
            self.last_refill_timestamp.clear()

            # If stats tracking is enabled, clear all stats and request history
            if self.enable_stats:
                self.stats.clear()
                self.request_history.clear()

        # Reinitialize tokens and refill timestamps for the specific key or all keys
        keys_to_reset = [key] if key else list(self.tokens.keys())
        
        # Reset tokens and refill timestamps for the specified keys
        for k in keys_to_reset:
            self.tokens[k] = self.capacity + self.burst 
            self.last_refill_timestamp[k] = now

    # Method to update the capacity of the token bucket
    def update_capacity(self, new_capacity: int):
        # Ensure the new capacity is greater than zero
        if new_capacity <= 0:
            raise ValueError("The capacity must be greater than zero.")
        # Update the capacity to the new value
        self.capacity = new_capacity

    # Method to update the burst size (extra tokens that can be used in addition to the regular capacity)
    def update_burst(self, new_burst: int):
        # Ensure the new burst size is non-negative
        if new_burst < 0:
            raise ValueError("The burst must be greater than or equal to zero.")
        # Update the burst size to the new value
        self.burst = new_burst

        # For each key, adjust the token count to account for the new burst size
        for key in self.tokens:
            self.tokens[key] = min(self.tokens[key] + new_burst, self.capacity + new_burst)

    # Method to update the stats window (the time window for tracking statistics)
    def update_stats_window(self, new_stats_window: int):
        # Ensure the new stats window is greater than zero
        if new_stats_window <= 0:
            raise ValueError("The stats window must be greater than zero.")
        # Update the stats window to the new value
        self.stats_window = new_stats_window

        # If stats tracking is enabled, resize the request history deque for each key
        if self.enable_stats:
            for key in self.request_history:
                # Update the deque to only retain the last `new_stats_window` entries
                self.request_history[key] = deque(self.request_history[key], maxlen=new_stats_window)

    # Method to update the time period over which tokens are refilled
    def update_time(self, seconds: int = 0, minutes: int = 0, hours: int = 0):
        # Calculate the total time in seconds from the provided hours, minutes, and seconds
        new_time = (seconds) + (minutes * 60) + (hours * 3600)
        # Ensure the new time period is greater than zero
        if new_time <= 0:
            raise ValueError("The total time must be greater than zero.")
        
        # Get the old time period
        old_time = self.time
        self.time = new_time

        now = time_module.time()

        # Recalculate the token count for each key based on the new time period
        for key in self.tokens.keys():
            elapsed_time = now - self.last_refill_timestamp[key]
            # Calculate the old tokens, factoring in the old time and rate
            old_tokens = min(self.capacity + self.burst, self.tokens[key] + elapsed_time * (self.rate / old_time))
            # Adjust tokens to the new time rate
            new_tokens = old_tokens * (old_time / new_time)
            self.tokens[key] = min(self.capacity + self.burst, new_tokens)
            self.last_refill_timestamp[key] = now

    # Method to update the rate at which tokens are refilled
    def update_rate(self, new_rate: int):
        # Ensure the new rate is a valid positive integer
        if new_rate <= 0:
            raise ValueError("The rate must be greater than zero.")

        # Store the old rate and update the rate to the new value
        old_rate = self.rate
        self.rate = new_rate

        # Get the current time
        now = time_module.time()

        # Recalculate the token count for each key based on the new rate
        for key in self.tokens.keys():
            elapsed_time = now - self.last_refill_timestamp[key]
            # Calculate the old tokens based on the old rate and elapsed time
            old_tokens = min(self.capacity + self.burst, self.tokens[key] + elapsed_time * (old_rate / self.time))
            # Adjust tokens proportionally to the new rate
            new_tokens = old_tokens * (old_rate / new_rate)
            self.tokens[key] = min(self.capacity + self.burst, new_tokens)
            self.last_refill_timestamp[key] = now

    # Implement the get_key_from_request method
    def get_key_from_request(self, request: Request) -> str:
        # Return the client's host if available, otherwise return "default"
        return request.client.host if request.client else "default"

    # Implement the enable_stats_collection method
    def enable_stats_collection(self):
        # Enable stats collection if not already enabled
        if not self.enable_stats:
            self.enable_stats = True
            # Preserve existing stats if available
            if not hasattr(self, 'stats'):
                self.stats = defaultdict(RequestStats)
            # Preserve existing request history if available
            if not hasattr(self, 'request_history'):
                self.request_history = defaultdict(lambda: deque(maxlen=self.stats_window))

    # Implement the disable_stats_collection method
    def disable_stats_collection(self):
        # Disable stats collection
        self.enable_stats = False

    # Implement the trigger_callbacks method
    async def trigger_callbacks(self, allowed: bool, key: str):
        # Iterate over each registered callback
        for callback in self.callbacks:
            try:
                # Check if the callback is asynchronous, await if necessary
                if asyncio.iscoroutinefunction(callback):
                    await callback(allowed, key)
                else:
                    callback(allowed, key)
            except Exception as e:
                print(f"Error in rate limiter callback: {e}")

    # Implement the add_callback method
    def add_callback(self, callback: Callable):
        # Add a new callback function to the list of callbacks
        self.callbacks.append(callback)
    
    # Method to create a rate-limiting decorator for FastAPI routes
    def limit(self):
        # Inner decorator function that wraps the actual route handler
        def decorator(func):
            # Asynchronous wrapper function to handle rate-limiting logic
            async def wrapper(request: Request):
                key = self.get_key_from_request(request)
                try:
                    # Try to allow the request based on rate-limiting logic
                    await self.allow_request(key)
                    # If allowed, proceed to call the original route handler
                    return await func(request)
                except HTTPException as exc:
                    # If rate-limiting throws an exception, return a JSON response with the error
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail}
                    )
            return wrapper
        return decorator

    # Middleware for FastAPI to apply rate-limiting to all incoming requests
    async def fastapi_middleware(self, request: Request, call_next: Callable):
        key = self.get_key_from_request(request)
        try:
            # Try to allow the request based on rate-limiting logic
            await self.allow_request(key)
            # If allowed, proceed to the next middleware or route handler
            response = await call_next(request)
            # Return the response
            return response
        except HTTPException as exc:
            # If rate-limiting throws an exception, return a JSON response with the error
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        
# Implement the setup_rate_limiter function
def setup_rate_limiter(app: FastAPI, rate_limiter: RateLimiter):
    # Define and attach the rate limiter middleware to the FastAPI app
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Callable):
        # Call the rate limiter middleware with the current request and the next callable
        return await rate_limiter.fastapi_middleware(request, call_next)
