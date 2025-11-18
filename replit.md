# Multi-Threaded Web Server with Real-Time Dashboard

## Overview

This project is a production-ready, multi-threaded web server implementation demonstrating advanced Operating Systems concepts including concurrency, thread pooling, and real-time monitoring. The system consists of three main components:

1. **Python-based Web Server** - A custom TCP socket server with thread pool architecture for handling concurrent HTTP requests
2. **Flask Dashboard** - A real-time monitoring interface for server metrics and performance visualization
3. **React Frontend** (in development) - A modern dashboard interface built with React, TypeScript, and Tailwind CSS using Vite

The project serves as both an educational demonstration of OS concepts and a functional web server with performance monitoring capabilities.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture

**Multi-Threaded Web Server (`server/`)**
- **Core Technology**: Python socket programming with custom HTTP implementation
- **Concurrency Model**: Fixed-size thread pool (default 10 workers) using a queue-based task distribution system
- **Design Pattern**: Producer-consumer pattern where the main server thread accepts connections and worker threads process requests
- **Rationale**: Thread pooling prevents resource exhaustion from unlimited thread creation while maintaining efficient concurrent request handling

**Thread Pool Implementation (`server/threadpool.py`)**
- Custom thread pool class managing worker threads and task queue
- Uses Python's `queue.Queue` for thread-safe task distribution
- Graceful shutdown mechanism with timeout handling
- **Advantage**: Reuses threads rather than creating/destroying for each request, reducing overhead

**Request Processing**
- Static file serving from `server/static/` directory
- In-memory file caching with toggle functionality
- HTTP status code tracking (200, 400, 404, 500)
- Cookie-based session management with UUID generation
- **Design Choice**: Simple in-memory caching trades memory for speed; suitable for small-scale deployments

**Metrics & Monitoring**
- Thread-safe metrics collection using `threading.Lock`
- Real-time tracking of: active clients, response times, cache hit/miss ratios, status code distribution
- Simulated geo-distribution and device detection
- **Implementation**: Shared dictionary with lock-based synchronization ensures data consistency across threads

**Flask Dashboard (`dashboard/dashboard.py`)**
- REST API for metrics retrieval (`/metrics`)
- Load testing controls (`/start_test`, `/stop_test`)
- Cache toggle endpoint (`/toggle_cache`)
- Auto-starts the internal web server on initialization
- **Purpose**: Provides programmatic interface to server management and monitoring

### Frontend Architecture

**React Application (`src/`)**
- **Framework**: React 18 with TypeScript for type safety
- **Build Tool**: Vite for fast development and optimized production builds
- **Styling**: Tailwind CSS for utility-first styling
- **Current State**: Minimal starter template; intended to replace Flask templates with modern SPA

**Dashboard UI (`dashboard/templates/index.html`)**
- Server-side rendered HTML with Chart.js for visualization
- Tailwind CSS via CDN for styling
- Real-time updates via polling (fetches `/metrics` endpoint every second)
- Features: live graphs, load testing controls, cache management
- **Design Choice**: Simple server-side rendering for quick deployment; planned migration to React frontend

### Client Simulation

**Load Testing (`client/client_simulator.py`)**
- Simulates concurrent clients with configurable parameters
- Three load patterns: continuous, burst, spike
- Configurable client count, request paths, and timing
- **Purpose**: Performance testing and stress testing the server's concurrent handling capabilities

### Performance Reporting

**Metrics Persistence (`reports/performance_report.py`)**
- JSON-based test results storage
- Matplotlib for performance graph generation
- Tracks historical data (up to 50 test runs)
- **Limitation**: File-based storage; no database for simplicity

## External Dependencies

### Python Dependencies
- **flask**: Web framework for the dashboard backend
- **matplotlib**: Performance graph generation and visualization
- Standard library: `socket`, `threading`, `queue`, `logging`, `json`

### Node.js/React Dependencies
- **@supabase/supabase-js**: Supabase client (currently unused, suggests planned backend integration)
- **react & react-dom**: Frontend framework
- **vite**: Build tool and development server
- **TypeScript**: Type safety for frontend code
- **Tailwind CSS**: Utility-first CSS framework
- **lucide-react**: Icon library
- **Chart.js**: Data visualization (used in Flask template via CDN)

### Development Tools
- **ESLint**: Code linting with TypeScript support
- **PostCSS & Autoprefixer**: CSS processing for Tailwind

### Future Integration Points
The presence of Supabase client suggests planned features:
- Database persistence for metrics and test results
- User authentication for dashboard access
- Real-time subscriptions for live metrics updates
- Cloud deployment with managed backend

### Deployment Architecture
- **Development**: Dual-server setup (Flask on port 5000, Web server on port 8080)
- **Orchestration**: `run_all.py` script manages component startup
- **Logging**: File-based logging to `logs/server.log`
- **No containerization**: Direct Python execution (Docker could be added for production)