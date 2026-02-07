# NEXUS - Future Hardware Store

A polyglot e-commerce platform built with Flask, using MongoDB for product catalogs (NoSQL) and PostgreSQL for transactional orders (SQL).

## Features

- **Polyglot Persistence:** MongoDB + PostgreSQL
- **Frontend:** Tailwind CSS + Alpine.js
- **Dynamic UI:** HTMX for cart drawers and filters
- **Architecture:** Service Layer Pattern

## Setup

1. **Clone and Install**

    ```bash
    git clone ...
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    ```

2. **Environment**
Create a `.env` file (see `.env.example`).

3. **Start Databases**

    ```bash
    docker-compose up -d
    ```

4. **Initialize DB & Seed Data**

    ```bash
    flask db upgrade
    python seed.py
    ```

5. **Run**

    ```bash
    python run.py
    ```
