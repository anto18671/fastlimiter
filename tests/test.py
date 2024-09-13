from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from collections import deque
import threading
import asyncio
import uvicorn
import pytest
import httpx
import time
import sys
import os

# Add the parent directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the rate limiter and FastAPI integration
from fastlimiter.fastlimiter import RateLimiter, setup_rate_limiter

# Fixtures
@pytest.fixture
def rate_limiter():
    return RateLimiter(
        rate=10,
        seconds=60,
        capacity=10,
        burst=5,
        stats_window=20,
        enable_stats=True
    )

# Fixtures for FastAPI integration
@pytest.fixture
def app(rate_limiter):
    app = FastAPI()
    
    rate_limiter_limited = RateLimiter(
        rate=10,
        seconds=60,
        capacity=10,
        burst=5,
        stats_window=20,
        enable_stats=True
    )

    setup_rate_limiter(app, rate_limiter)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {"message": "Test endpoint"}

    @app.get("/limited")
    @rate_limiter_limited.limit()
    async def limited_endpoint(request: Request):
        return {"message": "Limited endpoint"}

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    return app

@pytest.fixture
def client(app):
    return TestClient(app)

# ------- Basic functionality tests ------- #
@pytest.mark.asyncio
async def test_invalid_rate(rate_limiter):
    with pytest.raises(ValueError):
        RateLimiter(rate=0, seconds=60)
        
    with pytest.raises(ValueError):
        RateLimiter(rate=-1, seconds=60)
        
@pytest.mark.asyncio
async def test_invalid_capacity(rate_limiter):
    with pytest.raises(ValueError):
        RateLimiter(rate=5, capacity=0, seconds=60)
        
    with pytest.raises(ValueError):
        RateLimiter(rate=5, capacity=-1, seconds=60)
        
@pytest.mark.asyncio
async def test_invalid_rate_time(rate_limiter):
    invalid_cases = [
        {"rate": 5, "seconds": 0, "minutes": 0, "hours": 0},        # No time provided

        {"rate": 5, "seconds": 0},                                  # 0 seconds
        {"rate": 5, "seconds": -1},                                 # -1 second
        {"rate": 5, "minutes": 0},                                  # 0 minutes
        {"rate": 5, "minutes": -1},                                 # -1 minute
        {"rate": 5, "hours": 0},                                    # 0 hours
        {"rate": 5, "hours": -1},                                   # -1 hour

        {"rate": 5, "seconds": -30, "minutes": 0, "hours": 0},      # Total = -30 seconds
        {"rate": 5, "seconds": 0, "minutes": -1, "hours": 0},       # Total = -1 minute
        {"rate": 5, "seconds": 0, "minutes": 0, "hours": -1},       # Total = -1 hour
        {"rate": 5, "seconds": 3600, "hours": -1},                  # Total = 0 (1 hour - 1 hour)
        {"rate": 5, "minutes": 120, "hours": -2},                   # Total = 0 (2 hours - 2 hours)
        {"rate": 5, "seconds": 1800, "hours": -1},                  # Total = -30 minutes (1 hour - 30 min)
        {"rate": 5, "seconds": 0, "minutes": -120, "hours": 2},     # Total = 0 (2 hours - 2 hours)
        {"rate": 5, "seconds": -120, "minutes": 2},                 # Total = 0 (2 min - 2 min)
        {"rate": 5, "seconds": -120, "minutes": 1, "hours": 0},     # Total = -1 minute (2 min - 2 min)
        {"rate": 5, "seconds": -3600, "minutes": 59, "hours": 0},   # Total = -1 minutes
        {"rate": 5, "seconds": 30, "minutes": -1, "hours": 0},      # Total = -30 seconds
    ]
    
    for case in invalid_cases:
        with pytest.raises(ValueError):
            RateLimiter(**case)
    
@pytest.mark.asyncio
async def test_valid_rate_time(rate_limiter):
    valid_cases = [
        {"rate": 5, "seconds": 30},                                 # Total = 30 seconds
        {"rate": 5, "minutes": 1},                                  # Total = 1 minute
        {"rate": 5, "hours": 1},                                    # Total = 1 hour
        
        {"rate": 5, "seconds": 30, "minutes": 1},                   # Total = 1 min 30 seconds
        {"rate": 5, "minutes": 1, "hours": 1},                      # Total = 1 hour 1 minute
        {"rate": 5, "seconds": 3600, "hours": 1},                   # Total = 2 hours
        
        {"rate": 5, "minutes": -1, "seconds": 120},                 # Total = 1 minute (2 min - 1 min)
        {"rate": 5, "hours": -1, "seconds": 7200},                  # Total = 1 hour (2 hours - 1 hour)
        {"rate": 5, "minutes": -30, "hours": 2},                    # Total = 1 hour 30 minutes
        {"rate": 5, "seconds": -120, "minutes": 3},                 # Total = 1 minute (3 min - 2 min)
        {"rate": 5, "hours": -1, "minutes": 90},                    # Total = 30 minutes (1.5 hours - 1 hour)
        {"rate": 5, "seconds": 300, "minutes": -5, "hours": 1},     # Total = 1 hour (1 hour + 5 min - 5 min)
    ]
    
    for case in valid_cases:
        try:
            RateLimiter(**case)
        except ValueError:
            pytest.fail(f"RateLimiter raised ValueError unexpectedly for case: {case}")
            
@pytest.mark.asyncio
async def test_multiple_time_units(rate_limiter):
    previous_rate = rate_limiter.rate
    previous_burst = rate_limiter.burst
    previous_capacity = rate_limiter.capacity
    previous_time = rate_limiter.time

    rate_limiter.update_rate(60)
    rate_limiter.update_burst(0)
    rate_limiter.update_capacity(60)
    rate_limiter.update_time(seconds=30, minutes=1, hours=0.5)

    assert rate_limiter.time == 30 + 60 + 1800, "Time calculation incorrect for multiple units"

    key = "test_user"
    rate_limiter.reset(key)

    for _ in range(60):
        await rate_limiter.allow_request(key)
        print(f"Tokens after request {_ + 1}: {rate_limiter.tokens[key]}")

    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

    rate_limiter.update_rate(previous_rate)
    rate_limiter.update_burst(previous_burst)
    rate_limiter.update_capacity(previous_capacity)
    rate_limiter.update_time(seconds=previous_time)
        
@pytest.mark.asyncio
async def test_invalid_burst(rate_limiter):
    with pytest.raises(ValueError):
        RateLimiter(rate=5, seconds=60, burst=-1)
        
@pytest.mark.asyncio
async def test_invalid_stats_window(rate_limiter):
    with pytest.raises(ValueError):
        RateLimiter(rate=5, seconds=60, stats_window=0)
        
    with pytest.raises(ValueError):
        RateLimiter(rate=5, seconds=60, stats_window=-1)

@pytest.mark.asyncio
async def test_basic_rate_limiting(rate_limiter):
    key = "test_user"
    allowed_count = 0
    for i in range(15):
        try:
            _ = await rate_limiter.allow_request(key)
            allowed_count += 1
            print(f"Request {i+1}: Allowed")
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")
    
    assert allowed_count == 15, f"Expected 15 allowed requests, got {allowed_count}"
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

@pytest.mark.asyncio
async def test_burst_capacity(rate_limiter):
    key = "test_user"
    allowed_count = 0
    for i in range(15):
        try:
            _ = await rate_limiter.allow_request(key)
            allowed_count += 1
            print(f"Request {i+1}: Allowed")
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")
    
    assert allowed_count == 15, f"Expected 15 allowed requests (10 regular + 5 burst), got {allowed_count}"
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

@pytest.mark.asyncio
async def test_edge_case_dynamic_updates(rate_limiter):
    key = "test_user"

    previous_rate = rate_limiter.rate
    previous_burst = rate_limiter.burst
    previous_capacity = rate_limiter.capacity

    rate_limiter.update_rate(1000)
    rate_limiter.update_burst(0)
    rate_limiter.update_capacity(1000)
    rate_limiter.reset(key)

    requests_made = 0
    try:
        while True:
            await rate_limiter.allow_request(key)
            requests_made += 1
    except HTTPException:
        pass

    rate_limiter.update_rate(previous_rate)
    rate_limiter.update_burst(previous_burst)
    rate_limiter.update_capacity(previous_capacity)

    assert requests_made == 1000, f"Expected exactly 1000 requests, got {requests_made}"

@pytest.mark.asyncio
async def test_consistency_across_resets(rate_limiter):
    key = "test_user"
    
    for _ in range(15):
        await rate_limiter.allow_request(key)
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    rate_limiter.reset(key)
    
    for _ in range(15):
        await rate_limiter.allow_request(key)
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

@pytest.mark.asyncio
async def test_behavior_near_capacity_limits(rate_limiter):
    key = "test_user"
    
    for _ in range(14):
        await rate_limiter.allow_request(key)
    
    await rate_limiter.allow_request(key)
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

@pytest.mark.asyncio
async def test_stats_collection(rate_limiter):
    key = "test_user"
    for i in range(15):
        try:
            await rate_limiter.allow_request(key)
            print(f"Request {i+1}: Allowed")
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")

    stats = rate_limiter.get_stats(key)
    print(f"Stats: {stats}")
    assert stats["total_allowed"] == 15, f"Expected 15 allowed requests, got {stats['total_allowed']}"
    assert stats["total_denied"] == 0, f"Expected 0 denied requests, got {stats['total_denied']}"

@pytest.mark.asyncio
async def test_reset_functionality(rate_limiter):
    key = "test_user"
    for i in range(15):
        try:
            await rate_limiter.allow_request(key)
            print(f"Request {i+1}: Allowed")
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    rate_limiter.reset(key)
    print("Rate limiter reset")
    
    result = await rate_limiter.allow_request(key)
    assert result, "Request should be allowed after reset"

@pytest.mark.asyncio
async def test_multiple_keys(rate_limiter):
    key1 = "user1"
    key2 = "user2"
    
    for i in range(15):
        try:
            _ = await rate_limiter.allow_request(key1)
            print(f"Request {i+1} for key1: Allowed")
        except HTTPException as e:
            print(f"Request {i+1} for key1: Denied - {e.detail}")
        
        try:
            _ = await rate_limiter.allow_request(key2)
            print(f"Request {i+1} for key2: Allowed")
        except HTTPException as e:
            print(f"Request {i+1} for key2: Denied - {e.detail}")
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key1)
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key2)

@pytest.mark.asyncio
async def test_get_wait_time(rate_limiter):
    key = "test_user"
    for i in range(15):
        try:
            await rate_limiter.allow_request(key)
            print(f"Request {i+1}: Allowed")
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")
    
    wait_time = await rate_limiter.get_wait_time(key)
    print(f"Wait time: {wait_time}")
    assert wait_time > 0, f"Wait time should be greater than 0 after exceeding limit, got {wait_time}"

@pytest.mark.asyncio
async def test_disable_enable_stats(rate_limiter):
    key = "test_user"
    await rate_limiter.allow_request(key)
    
    stats = rate_limiter.get_stats(key)
    print(f"Initial stats: {stats}")
    assert stats is not None, "Stats should be available"
    
    rate_limiter.disable_stats_collection()
    disabled_stats = rate_limiter.get_stats(key)
    print(f"Disabled stats: {disabled_stats}")
    assert disabled_stats == {"error": "Stats collection is disabled"}, "Stats should be disabled"
    
    rate_limiter.enable_stats_collection()
    await rate_limiter.allow_request(key)
    enabled_stats = rate_limiter.get_stats(key)
    print(f"Enabled stats: {enabled_stats}")
    assert enabled_stats is not None, "Stats should be available after re-enabling"
    
@pytest.mark.asyncio
async def test_rate_limiter_refill(rate_limiter):
    key = "test_user"
    
    for _ in range(10):
        await rate_limiter.allow_request(key)

    await asyncio.sleep(5)
    
    allowed_count = 0
    for _ in range(5):
        try:
            await rate_limiter.allow_request(key)
            allowed_count += 1
        except HTTPException:
            pass
    
    assert allowed_count > 0, "Requests should be allowed after token refill"

# ------- FastAPI integration tests ------- #
def test_middleware_rate_limiting(client):
    for i in range(15):
        response = client.get("/test")
        assert response.status_code == 200, f"Request {i+1} should be allowed"

    response = client.get("/test")
    assert response.status_code == 429, "Request should be rate limited"
    assert "Rate limit exceeded" in response.json()["detail"]

@pytest.mark.asyncio
async def test_decorator_rate_limiting(client, rate_limiter):
    key = "testclient"

    rate_limiter.reset(key)

    for i in range(15):
        response = client.get("/limited")
        assert response.status_code == 200, f"Request {i+1} should be allowed. Content: {response.json()}"
        await asyncio.sleep(0.1)

    response = client.get("/limited")

    assert response.status_code == 429, f"Request 16 should be rate-limited, but got {response.status_code}"

def test_different_endpoints(client):
    for _ in range(15):
        client.get("/test")

    for _ in range(7):
        client.get("/limited")

    response = client.get("/test")
    assert response.status_code == 429, "/test should be rate limited"

    response = client.get("/limited")
    assert response.status_code == 429, "/limited should be rate limited"

def test_rate_limit_reset(client, rate_limiter):
    for _ in range(15):
        client.get("/test")

    response = client.get("/test")
    assert response.status_code == 429, "Request should be rate limited"

    rate_limiter.reset("testclient")

    response = client.get("/test")
    assert response.status_code == 200, "Request should be allowed after reset"
    
@pytest.mark.asyncio
async def test_rate_limiter_with_multiple_clients(rate_limiter):
    async def make_request(client_id):
        try:
            _ = await rate_limiter.allow_request(client_id)
            print(f"Request for {client_id}: Allowed")
        except HTTPException as e:
            print(f"Request for {client_id}: Denied - {e.detail}")

    clients = ["client_1", "client_2", "client_3", "client_4", "client_5"]
    
    for _ in range(16):
        tasks = [make_request(client) for client in clients]
        await asyncio.gather(*tasks)

    for client in clients:
        with pytest.raises(HTTPException):
            await rate_limiter.allow_request(client)

@pytest.mark.asyncio
async def test_stats_window_tracking(rate_limiter):
    key = "test_user"
    
    for _ in range(5):
        await rate_limiter.allow_request(key)
    
    stats = rate_limiter.get_stats(key)
    assert stats["window_allowed"] == 5, "Stats should track 5 allowed requests in the window"
    
    await asyncio.sleep(rate_limiter.stats_window)
    
    stats = rate_limiter.get_stats(key)
    assert stats["window_allowed"] == 0, "Stats window should reset after elapsed time"
    
@pytest.mark.asyncio
async def test_stats_cleared_on_reset(rate_limiter):
    key = "test_user"
    
    for _ in range(5):
        await rate_limiter.allow_request(key)

    rate_limiter.reset(key)
    
    stats = rate_limiter.get_stats(key)
    assert stats["total_allowed"] == 0, "Total allowed requests should be reset to 0"
    assert stats["total_denied"] == 0, "Total denied requests should be reset to 0"
    
@pytest.mark.asyncio
async def test_cleanup_of_unused_keys(rate_limiter):
    for i in range(10000):
        key = f"unique_key_{i}"
        await rate_limiter.allow_request(key)
    
    import sys
    memory_usage = sys.getsizeof(rate_limiter.tokens) + sys.getsizeof(rate_limiter.last_refill_timestamp)
    assert memory_usage < 1000000, "Memory usage too high, unused keys may not be cleaned up"

@pytest.mark.asyncio
async def test_concurrent_updates(rate_limiter):
    key = "test_user"
    
    async def make_request_and_update():
        try:
            await rate_limiter.allow_request(key)
        except HTTPException:
            pass
        rate_limiter.update_rate(rate_limiter.rate + 1)
    
    tasks = [make_request_and_update() for _ in range(100)]
    await asyncio.gather(*tasks)
    
    assert rate_limiter.rate == 110, "Rate should have been updated 100 times"

@pytest.mark.asyncio
async def test_time_shift_handling(rate_limiter):
    key = "test_user"

    for _ in range(10):
        await rate_limiter.allow_request(key)

    rate_limiter.last_refill_timestamp[key] += 3600

    for _ in range(5):
        await rate_limiter.allow_request(key)

    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

@pytest.mark.asyncio
async def test_stats_collection_during_rate_changes(rate_limiter):
    key = "test_user"
    
    for _ in range(10):
        await rate_limiter.allow_request(key)
    
    rate_limiter.update_rate(5)
    
    for _ in range(5):
        try:
            await rate_limiter.allow_request(key)
        except HTTPException:
            pass
    
    stats = rate_limiter.get_stats(key)
    assert stats["total_allowed"] == 15, "Stats should account for requests before and after rate change"

@pytest.mark.asyncio
async def test_multiple_stats_collection_toggles(rate_limiter):
    key = "test_user"
    
    previous_capacity = rate_limiter.capacity
    rate_limiter.update_capacity(100)
    
    for _ in range(5):
        await rate_limiter.allow_request(key)
    
    initial_stats = rate_limiter.get_stats(key)
    assert initial_stats["total_allowed"] == 5, "Initial stats should show 5 allowed requests"
    
    rate_limiter.disable_stats_collection()
    
    for _ in range(5):
        await rate_limiter.allow_request(key)
    
    rate_limiter.enable_stats_collection()
    
    for _ in range(5):
        await rate_limiter.allow_request(key)
    
    mid_stats = rate_limiter.get_stats(key)
    assert mid_stats["total_allowed"] == 10, "Stats should show 10 allowed requests after re-enabling"
    
    rate_limiter.disable_stats_collection()
    
    for _ in range(5):
        await rate_limiter.allow_request(key)
    
    rate_limiter.enable_stats_collection()
    
    final_stats = rate_limiter.get_stats(key)
    
    rate_limiter.update_capacity(previous_capacity)
    assert final_stats["total_allowed"] == 10, "Final stats should still show 10 allowed requests"

@pytest.mark.asyncio
async def test_callback_execution(rate_limiter):
    key = "test_user"
    callback_results = []
    
    def sync_callback(allowed, key):
        callback_results.append(("sync", allowed, key))
    
    async def async_callback(allowed, key):
        callback_results.append(("async", allowed, key))
    
    rate_limiter.add_callback(sync_callback)
    rate_limiter.add_callback(async_callback)
    
    await rate_limiter.allow_request(key)
    
    for _ in range(14):
        await rate_limiter.allow_request(key)
        
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    assert len(callback_results) == 32, "Callbacks should be executed for each request"
    assert ("sync", True, key) in callback_results, "Sync callback should be called for allowed request"
    assert ("async", True, key) in callback_results, "Async callback should be called for allowed request"
    assert ("sync", False, key) in callback_results, "Sync callback should be called for denied request"
    assert ("async", False, key) in callback_results, "Async callback should be called for denied request"

# ------- Advanced scenarios and edge cases ------- #
@pytest.mark.asyncio
async def test_simultaneous_requests(rate_limiter):
    key = "test_user"

    async def make_request():
        try:
            _ = await rate_limiter.allow_request(key)
            print(f"Request Allowed")
        except HTTPException as e:
            print(f"Request Denied - {e.detail}")

    tasks = [make_request() for _ in range(15)]
    await asyncio.gather(*tasks)

    stats = rate_limiter.get_stats(key)
    print(f"Stats after simultaneous requests: {stats}")
    assert stats["total_allowed"] == 15, "Expected all requests to be allowed within the burst"

@pytest.mark.asyncio
async def test_high_volume_over_time(rate_limiter):
    key = "test_user"
    allowed_count = 0

    for i in range(100):
        try:
            await asyncio.sleep(0.1)
            _ = await rate_limiter.allow_request(key)
            allowed_count += 1
        except HTTPException as e:
            print(f"Request {i+1}: Denied - {e.detail}")

    print(f"Total allowed requests: {allowed_count}")
    stats = rate_limiter.get_stats(key)
    assert stats["total_allowed"] <= 100, "Allowed requests should be limited within the rate limit"

@pytest.mark.asyncio
async def test_different_keys_overlapping(rate_limiter):
    key1 = "user1"
    key2 = "user2"

    async def make_request(key):
        try:
            _ = await rate_limiter.allow_request(key)
            print(f"Request for {key}: Allowed")
        except HTTPException as e:
            print(f"Request for {key}: Denied - {e.detail}")

    tasks = [make_request(key1), make_request(key2), make_request(key1), make_request(key2)]
    await asyncio.gather(*tasks)

    stats_key1 = rate_limiter.get_stats(key1)
    stats_key2 = rate_limiter.get_stats(key2)
    
    assert stats_key1["total_allowed"] == 2, "Both requests for key1 should be allowed"
    assert stats_key2["total_allowed"] == 2, "Both requests for key2 should be allowed"

@pytest.mark.asyncio
async def test_wait_time_calculation(rate_limiter):
    key = "test_user"

    for _ in range(15):
        try:
            await rate_limiter.allow_request(key)
        except HTTPException:
            pass

    wait_time = await rate_limiter.get_wait_time(key)
    print(f"Calculated wait time: {wait_time}")
    assert wait_time > 0, "Wait time should be greater than zero after exceeding limit"

@pytest.mark.asyncio
async def test_stats_reset_on_key(rate_limiter):
    key = "test_user"

    for _ in range(10):
        await rate_limiter.allow_request(key)

    stats_before = rate_limiter.get_stats(key)
    assert stats_before["total_allowed"] == 10, f"Expected 10 allowed requests, got {stats_before['total_allowed']}"

    rate_limiter.reset(key)

    stats_after = rate_limiter.get_stats(key)
    assert stats_after["total_allowed"] == 0, "Stats should be reset to 0 after reset"
    
@pytest.mark.asyncio
async def test_dynamic_rate_change(rate_limiter):
    key = "test_user"
    
    rate_limiter.reset(key)
    initial_rate = rate_limiter.rate
    initial_capacity = rate_limiter.capacity
    initial_burst = rate_limiter.burst
    
    for _ in range(initial_capacity + initial_burst):
        await rate_limiter.allow_request(key)
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    new_rate = initial_rate * 2
    rate_limiter.update_rate(new_rate)
    
    assert rate_limiter.rate == new_rate, f"Expected rate to be {new_rate}, got {rate_limiter.rate}"
    
    await asyncio.sleep(rate_limiter.time / new_rate)
    
    await rate_limiter.allow_request(key)
    
    rate_limiter.update_rate(initial_rate)
    
@pytest.mark.asyncio
async def test_dynamic_capacity_change(rate_limiter):
    key = "test_user"

    rate_limiter.reset(key)
    initial_capacity = rate_limiter.capacity
    initial_burst = rate_limiter.burst
    total_initial_tokens = initial_capacity + initial_burst

    for _ in range(total_initial_tokens):
        await rate_limiter.allow_request(key)

    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

    new_capacity = initial_capacity * 2
    rate_limiter.update_capacity(new_capacity)

    assert rate_limiter.capacity == new_capacity, f"Expected capacity to be {new_capacity}, got {rate_limiter.capacity}"

    await asyncio.sleep(rate_limiter.time / rate_limiter.rate)

    additional_allowed = 0
    for _ in range(new_capacity - initial_capacity):
        try:
            await rate_limiter.allow_request(key)
            additional_allowed += 1
        except HTTPException:
            break

    assert additional_allowed > 0, f"Expected to allow additional requests after increasing capacity, but got {additional_allowed}"

    lower_capacity = initial_capacity // 2
    rate_limiter.update_capacity(lower_capacity)

    assert rate_limiter.capacity == lower_capacity, f"Expected capacity to be {lower_capacity}, got {rate_limiter.capacity}"

    rate_limiter.reset(key)
    allowed_count = 0
    for _ in range(lower_capacity + initial_burst):
        try:
            await rate_limiter.allow_request(key)
            allowed_count += 1
        except HTTPException:
            break

    assert allowed_count == lower_capacity + initial_burst, f"Expected {lower_capacity + initial_burst} allowed requests after decreasing capacity, but got {allowed_count}"

    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

    rate_limiter.update_capacity(initial_capacity)

@pytest.mark.asyncio
async def test_dynamic_time_change(rate_limiter):
    key = "test_user"
    
    rate_limiter.reset(key)
    initial_time = rate_limiter.time
    initial_capacity = rate_limiter.capacity
    initial_burst = rate_limiter.burst
    
    for _ in range(initial_capacity + initial_burst):
        await rate_limiter.allow_request(key)
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    new_time_seconds = initial_time * 2
    rate_limiter.update_time(seconds=new_time_seconds)
    
    assert rate_limiter.time == new_time_seconds, f"Expected time to be {new_time_seconds}, got {rate_limiter.time}"
    
    await asyncio.sleep(initial_time / rate_limiter.rate)
    
    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)
    
    await asyncio.sleep(initial_time / rate_limiter.rate)
    
    await rate_limiter.allow_request(key)
    
    rate_limiter.update_time(seconds=initial_time)
    
@pytest.mark.asyncio
async def test_dynamic_burst_change(rate_limiter):
    key = "test_user"

    rate_limiter.reset(key)
    initial_capacity = rate_limiter.capacity
    initial_burst = rate_limiter.burst

    for _ in range(initial_capacity):
        await rate_limiter.allow_request(key)

    for _ in range(initial_burst):
        await rate_limiter.allow_request(key)

    with pytest.raises(HTTPException):
        await rate_limiter.allow_request(key)

    new_burst = initial_burst * 2
    rate_limiter.update_burst(new_burst)

    assert rate_limiter.burst == new_burst, f"Expected burst to be {new_burst}, got {rate_limiter.burst}"

    additional_allowed = 0
    for _ in range(new_burst - initial_burst):
        try:
            await rate_limiter.allow_request(key)
            additional_allowed += 1
        except HTTPException:
            break

    assert additional_allowed == new_burst - initial_burst, f"Expected to allow {new_burst - initial_burst} additional requests after increasing burst, but got {additional_allowed}"

    rate_limiter.update_burst(initial_burst)

@pytest.mark.asyncio
async def test_dynamic_stats_window_change(rate_limiter):
    key = "test_user"

    rate_limiter.reset(key)
    initial_stats_window = rate_limiter.stats_window

    for _ in range(5):
        await rate_limiter.allow_request(key)

    await asyncio.sleep(initial_stats_window / 2)

    for _ in range(5):
        await rate_limiter.allow_request(key)

    initial_stats = rate_limiter.get_stats(key)
    assert initial_stats["window_allowed"] == 10, f"Expected 10 allowed requests in initial window, got {initial_stats['window_allowed']}"

    new_stats_window = initial_stats_window // 2
    rate_limiter.update_stats_window(new_stats_window)

    assert rate_limiter.stats_window == new_stats_window, f"Expected stats_window to be {new_stats_window}, got {rate_limiter.stats_window}"

    assert isinstance(rate_limiter.request_history[key], deque), "request_history should be a deque"
    assert rate_limiter.request_history[key].maxlen == new_stats_window, f"request_history maxlen should be {new_stats_window}, got {rate_limiter.request_history[key].maxlen}"

    updated_stats = rate_limiter.get_stats(key)
    assert updated_stats["window_allowed"] <= 10, f"Expected 10 or fewer allowed requests in updated window, got {updated_stats['window_allowed']}"

    rate_limiter.update_stats_window(initial_stats_window)
    
# ------- Security Tests ------- #
@pytest.fixture
def secure_rate_limiter():
    return RateLimiter(
        rate=10,
        seconds=60,
        capacity=10,
        burst=5,
        stats_window=20,
        enable_stats=True
    )

@pytest.fixture
def secure_app(secure_rate_limiter):
    app = FastAPI()
    setup_rate_limiter(app, secure_rate_limiter)

    @app.get("/secure-test")
    async def secure_test_endpoint(request: Request):
        return {"message": "Secure test endpoint"}

    return app

@pytest.fixture
def secure_client(secure_app):
    return TestClient(secure_app)

def test_ip_spoofing_prevention(secure_client):
    headers_1 = {"X-Forwarded-For": "192.168.1.1"}
    headers_2 = {"X-Forwarded-For": "192.168.1.2"}

    for _ in range(15):
        secure_client.get("/secure-test", headers=headers_1)

    response = secure_client.get("/secure-test", headers=headers_2)
    
    assert response.status_code == 429, "Rate limiter should not be fooled by X-Forwarded-For header"

@pytest.mark.asyncio
async def test_timing_attack_resistance(secure_rate_limiter):
    key = "test_user"

    start = asyncio.get_event_loop().time()
    await secure_rate_limiter.allow_request(key)
    allowed_time = asyncio.get_event_loop().time() - start

    for _ in range(14):
        await secure_rate_limiter.allow_request(key)

    start = asyncio.get_event_loop().time()
    with pytest.raises(HTTPException):
        await secure_rate_limiter.allow_request(key)
    denied_time = asyncio.get_event_loop().time() - start

    time_difference = abs(denied_time - allowed_time)
    assert time_difference < 0.1, "Time to process allowed and denied requests should be similar"

@pytest.mark.asyncio
async def test_key_exhaustion_prevention(secure_rate_limiter):
    for i in range(10000):
        key = f"unique_key_{i}"
        try:
            await secure_rate_limiter.allow_request(key)
        except HTTPException:
            pass

    assert await secure_rate_limiter.allow_request("test_key"), "Rate limiter should still function after many unique keys"

def test_header_injection_prevention(secure_client):
    malicious_headers = {
        "X-Forwarded-For": "192.168.1.1\r\nX-Custom-Header: Injected",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36\r\nX-Custom-Header: Injected"
    }

    response = secure_client.get("/secure-test", headers=malicious_headers)
    
    assert "X-Custom-Header" not in response.headers, "Rate limiter should not allow header injection"

@pytest.mark.asyncio
async def test_ddos_protection():
    def run_server(app, should_exit):
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="critical")
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        while not should_exit.is_set():
            server.run(sockets=None)

    app = FastAPI()

    rate_limiter = RateLimiter(
        rate=5,
        seconds=1,
        capacity=5,
        burst=2,
        stats_window=20,
        enable_stats=True,
    )

    setup_rate_limiter(app, rate_limiter)

    should_exit = threading.Event()

    server_thread = threading.Thread(target=run_server, args=(app, should_exit))
    server_thread.start()

    time.sleep(5)

    try:
        async with httpx.AsyncClient() as client:
            async def ddos_attack():
                tasks = []
                for _ in range(1000):
                    tasks.append(client.get("http://127.0.0.1:8000/test"))
                    await asyncio.sleep(0.001)
                return await asyncio.gather(*tasks, return_exceptions=True)

            responses = await ddos_attack()

        _ = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        denied = sum(1 for r in responses if isinstance(r, httpx.HTTPStatusError) and r.response.status_code == 429)
        errors = sum(1 for r in responses if isinstance(r, Exception) and not isinstance(r, httpx.HTTPStatusError))

        denied += errors

        assert denied > 900, f"Expected over 900 denied requests during DDoS simulation, got {denied}"

    finally:
        should_exit.set()
        server_thread.join(timeout=5)

@pytest.mark.asyncio
async def test_race_condition_handling(secure_rate_limiter):
    key = "test_user"

    async def make_request():
        try:
            await secure_rate_limiter.allow_request(key)
            return "allowed"
        except HTTPException:
            return "denied"

    tasks = [make_request() for _ in range(100)]
    results = await asyncio.gather(*tasks)

    allowed = results.count("allowed")
    assert allowed == 15, f"Expected exactly 15 allowed requests under concurrent load, got {allowed}"

if __name__ == "__main__":
    pytest.main([__file__])