# FastLimiter

[![PyPI version](https://img.shields.io/pypi/v/fastlimiter.svg?cacheSeconds=3600)](https://pypi.org/project/fastlimiter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fast and flexible token bucket rate limiter for FastAPI applications.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Install via Pip](#install-via-pip)
  - [Install from Source](#install-from-source)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
    - [As Middleware](#as-middleware)
    - [As Decorator](#as-decorator)
  - [Advanced Usage](#advanced-usage)
    - [Custom Key Function](#custom-key-function)
    - [Collecting Statistics](#collecting-statistics)
    - [Updating Parameters at Runtime](#updating-parameters-at-runtime)
- [API Reference](#api-reference)
  - [RateLimiter Class](#ratelimiter-class)
    - [Initialization](#initialization)
    - [Methods](#methods)
- [Configuration](#configuration)
- [Examples](#examples)
  - [Limiting Based on API Key](#limiting-based-on-api-key)
  - [Custom Callback Function](#custom-callback-function)
  - [Resetting Rate Limiter for a Specific Client](#resetting-rate-limiter-for-a-specific-client)
  - [Applying Different Limits to Different Endpoints](#applying-different-limits-to-different-endpoints)
  - [Limiting by User ID](#limiting-by-user-id)
  - [Customizing Rate Limit Exceeded Response](#customizing-rate-limit-exceeded-response)
- [Contributing](#contributing)
  - [Reporting Bugs](#reporting-bugs)
  - [Feature Requests](#feature-requests)
  - [Pull Requests](#pull-requests)
  - [Code Style](#code-style)
  - [Testing](#testing)
- [License](#license)
- [Contact](#contact)

## Features

- **Flexible Rate Limiting**: Configure rate limits based on tokens, capacity, burst size, and time intervals to suit different scenarios.
- **Token Bucket Algorithm**: Implements the efficient token bucket algorithm, which is ideal for handling bursts and smoothing out request rates.
- **FastAPI Integration**: Seamlessly integrates with FastAPI applications through middleware or route decorators.
- **Per-Client Limiting**: Rate limits are applied per client, identified by IP address or custom keys.
- **Statistics Collection**: Optionally collect detailed statistics, including allowed and denied requests, which can be used for monitoring and analytics.
- **Customizable Callbacks**: Add custom functions to execute after each request, allowing for logging, alerting, or other side effects.
- **Dynamic Configuration**: Update rate limiting parameters at runtime without restarting the application.

## Installation

### Prerequisites

- Python 3.8 or higher
- FastAPI 0.65.0 or higher

### Install via Pip

Install FastLimiter from PyPI:

```bash
pip install fastlimiter
```

### Install from Source

Alternatively, you can clone the repository and install it:

```bash
git clone https://github.com/anto18671/fastlimiter.git
cd fastlimiter
pip install .
```

## Quick Start

Here's how you can quickly get started with FastLimiter in your FastAPI application:

```python
from fastapi import FastAPI, Request
from fastlimiter import RateLimiter, setup_rate_limiter

app = FastAPI()

# Initialize the rate limiter
rate_limiter = RateLimiter(rate=10, capacity=100, seconds=60)

# Setup the rate limiter middleware
setup_rate_limiter(app, rate_limiter)

@app.get("/items")
async def read_items(request: Request):
    return {"message": "Hello, World!"}
```

In this example, the rate limiter allows up to 100 requests per client per 60 seconds, refilling at a rate of 10 tokens per 60 seconds.

## Usage

### Basic Usage

#### As Middleware

To apply rate limiting to all incoming requests, use the middleware:

```python
from fastapi import FastAPI
from fastlimiter import RateLimiter, setup_rate_limiter

app = FastAPI()

rate_limiter = RateLimiter(rate=5, capacity=10, seconds=60)
setup_rate_limiter(app, rate_limiter)
```

#### As Decorator

To apply rate limiting to specific routes, use the `limit` decorator:

```python
from fastapi import FastAPI, Request
from fastlimiter import RateLimiter

app = FastAPI()

rate_limiter = RateLimiter(rate=5, capacity=10, seconds=60)

@app.get("/limited")
@rate_limiter.limit()
async def limited_endpoint(request: Request):
    return {"message": "This endpoint is rate-limited."}
```

### Advanced Usage

#### Custom Key Function

You can customize how the rate limiter identifies clients by overriding `get_key_from_request`:

```python
def custom_key_function(self, request: Request) -> str:
    return request.headers.get("X-API-Key", "default")

rate_limiter.get_key_from_request = custom_key_function.__get__(rate_limiter, RateLimiter)
```

#### Collecting Statistics

Enable statistics collection to monitor rate limiting:

```python
rate_limiter.enable_stats_collection()

stats = rate_limiter.get_stats("client_key")
print(stats)
```

#### Updating Parameters at Runtime

You can dynamically update the rate limiter's parameters at runtime:

```python
rate_limiter.update_rate(new_rate=20)
rate_limiter.update_capacity(new_capacity=50)
rate_limiter.update_burst(new_burst=10)
rate_limiter.update_time(seconds=30)
rate_limiter.update_stats_window(new_stats_window=120)
```

## API Reference

### RateLimiter Class

#### Initialization

```python
RateLimiter(
    rate: int,
    capacity: int = 1024,
    burst: int = None,
    stats_window: int = 60,
    enable_stats: bool = True,
    seconds: int = 0,
    minutes: int = 0,
    hours: int = 0
)
```

- **rate** _(int)_: The rate at which tokens are added to the bucket.
- **capacity** _(int)_: Maximum number of tokens in the bucket.
- **burst** _(int, optional)_: Extra tokens allowed during bursts. Defaults to 0 if not provided.
- **stats_window** _(int, optional)_: Time window for collecting statistics in seconds.
- **enable_stats** _(bool, optional)_: Enable or disable statistics collection.
- **seconds**, **minutes**, **hours**: Define the time interval over which tokens are refilled.

#### Methods

##### allow_request(key: str) -> bool

Determines if a request identified by `key` is allowed based on the rate limit.

- **Parameters**:
  - `key` _(str)_: The unique identifier for the client/request.
- **Returns**:
  - `bool`: `True` if the request is allowed, `False` otherwise.
- **Raises**:
  - `HTTPException`: Raises an HTTP 429 exception if the request is denied.

##### get_wait_time(key: str) -> float

Returns the time in seconds a client identified by `key` needs to wait before making a new request.

- **Parameters**:
  - `key` _(str)_: The unique identifier for the client/request.
- **Returns**:
  - `float`: Time in seconds to wait before the next allowed request.

##### update_stats(key: str, allowed: bool, timestamp: float)

Updates the statistics for a given `key`.

- **Parameters**:
  - `key` _(str)_: The unique identifier for the client/request.
  - `allowed` _(bool)_: Whether the request was allowed.
  - `timestamp` _(float)_: The time when the request was processed.

##### get_stats(key: str) -> Dict

Retrieves the statistics for a given `key`.

- **Parameters**:
  - `key` _(str)_: The unique identifier for the client/request.
- **Returns**:
  - `Dict`: A dictionary containing statistical data such as total allowed, total denied, etc.

##### reset(key: str = None)

Resets the rate limiter state for a specific `key` or all keys if `key` is `None`.

- **Parameters**:
  - `key` _(str, optional)_: The unique identifier for the client/request. If `None`, resets all keys.

##### update_capacity(new_capacity: int)

Updates the capacity of the token bucket.

- **Parameters**:
  - `new_capacity` _(int)_: The new maximum number of tokens.

##### update_burst(new_burst: int)

Updates the burst size.

- **Parameters**:
  - `new_burst` _(int)_: The new burst size.

##### update_stats_window(new_stats_window: int)

Updates the time window for statistics collection.

- **Parameters**:
  - `new_stats_window` _(int)_: The new statistics window in seconds.

##### update_time(seconds: int = 0, minutes: int = 0, hours: int = 0)

Updates the time interval over which tokens are refilled.

- **Parameters**:
  - `seconds`, `minutes`, `hours`: Time components for the new interval.

##### update_rate(new_rate: int)

Updates the rate at which tokens are added to the bucket.

- **Parameters**:
  - `new_rate` _(int)_: The new token addition rate.

##### get_key_from_request(request: Request) -> str

Retrieves a unique key from the incoming request. By default, uses the client's IP address.

- **Parameters**:
  - `request` _(Request)_: The incoming FastAPI request.
- **Returns**:
  - `str`: The unique key for rate limiting.

##### enable_stats_collection()

Enables statistics collection.

##### disable_stats_collection()

Disables statistics collection.

##### add_callback(callback: Callable)

Adds a callback function to be executed after each request is processed.

- **Parameters**:
  - `callback` _(Callable)_: The function to call after processing a request.

##### limit()

Creates a rate-limiting decorator for FastAPI routes.

- **Returns**:
  - `Callable`: A decorator that can be applied to FastAPI route handlers.

##### fastapi_middleware(request: Request, call_next: Callable)

Middleware function to apply rate limiting to incoming FastAPI requests.

- **Parameters**:
  - `request` _(Request)_: The incoming FastAPI request.
  - `call_next` _(Callable)_: The next middleware or route handler.

## Configuration

Customize the rate limiter by adjusting the parameters:

- **Rate**: The number of tokens added to the bucket over the specified time interval.
- **Capacity**: The maximum number of tokens the bucket can hold.
- **Burst**: Additional tokens allowed for handling bursts of requests.
- **Time Interval**: The period over which tokens are refilled (specified in seconds, minutes, and/or hours).

Example:

```python
rate_limiter = RateLimiter(
    rate=100,
    capacity=200,
    burst=50,
    seconds=60,
    enable_stats=True,
    stats_window=300
)
```

## Examples

### Limiting Based on API Key

```python
def api_key_key_function(self, request: Request) -> str:
    return request.headers.get("X-API-Key", "anonymous")

rate_limiter.get_key_from_request = api_key_key_function.__get__(rate_limiter, RateLimiter)
```

### Custom Callback Function

```python
def log_request(allowed: bool, key: str):
    status = "allowed" if allowed else "denied"
    emoji = "😊" if allowed else "😞"
    print(f"Request from {key} was {status}. {emoji}")

rate_limiter.add_callback(log_request)
```

### Resetting Rate Limiter for a Specific Client

```python
rate_limiter.reset(key="client_ip")
```

### Applying Different Limits to Different Endpoints

```python
from fastapi import FastAPI, Request
from fastlimiter import RateLimiter

app = FastAPI()

# General rate limiter for most endpoints
general_limiter = RateLimiter(rate=100, capacity=200, seconds=60)

# Specific rate limiter for a heavy endpoint
heavy_limiter = RateLimiter(rate=10, capacity=20, seconds=60)

@app.get("/general")
@general_limiter.limit()
async def general_endpoint(request: Request):
    return {"message": "This is a general endpoint."}

@app.get("/heavy")
@heavy_limiter.limit()
async def heavy_endpoint(request: Request):
    return {"message": "This endpoint has stricter rate limiting."}
```

### Limiting by User ID

If your application uses authentication, you might want to rate limit based on user ID:

```python
def user_id_key_function(self, request: Request) -> str:
    user = request.state.user  # Assuming user is stored in request.state
    return str(user.id) if user else "anonymous"

rate_limiter.get_key_from_request = user_id_key_function.__get__(rate_limiter, RateLimiter)
```

### Customizing Rate Limit Exceeded Response

Customize the response when the rate limit is exceeded:

```python
from fastapi.responses import PlainTextResponse

async def rate_limit_middleware(request: Request, call_next: Callable):
    key = rate_limiter.get_key_from_request(request)
    try:
        await rate_limiter.allow_request(key)
        response = await call_next(request)
        return response
    except HTTPException as exc:
        return PlainTextResponse(
            "You have exceeded your request rate limit. Please try again later.",
            status_code=exc.status_code
        )

app.middleware("http")(rate_limit_middleware)
```

## Contributing

We welcome contributions to improve FastLimiter! Here's how you can contribute:

### Reporting Bugs

If you find a bug, please open an issue on [GitHub](https://github.com/anto18671/fastlimiter/issues) with detailed steps to reproduce the problem.

### Feature Requests

Have an idea for a new feature? Open an issue with the tag "enhancement" to discuss it.

### Pull Requests

1. Fork the repository on GitHub.
2. Clone your forked repository to your local machine.
3. Create a new branch for your changes: `git checkout -b feature/your-feature-name`.
4. Make your changes and commit them with clear messages.
5. Push your changes to your fork: `git push origin feature/your-feature-name`.
6. Open a pull request on the main repository.

### Code Style

Please follow the PEP 8 style guide for Python code.

### Testing

Ensure that all existing tests pass and write new tests for your code.

- Run tests with `pytest`.
- For asynchronous code, use `pytest_asyncio`.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For questions or suggestions, please open an issue on [GitHub](https://github.com/anto18671/fastlimiter/issues):

- **Author**: Anthony Therrien
