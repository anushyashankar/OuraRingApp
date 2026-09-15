# Oura Ring App
A full stack app that reads Oura data and explains it to you plainly!

My mom complained about her Oura ring after about a week of wearing it. When I asked her why, she showed me the app. As she scrolled though the various charts and metrics about her sleepy and activity, she said "I don't really know what a lot of this means. Why is it good or bad?"

Wearable apps tend to hand you a number and leave you to interpret it. A sleep score of 82 means nothing on its own — what matters is whether 82 is normal for you. Complicated words about sleep stages and wake after onset also aren't always accessible. This app computes that comparison against your own history, then uses a language model purely to phrase the result in everyday language.

The statistics are the engine; the model is only the interface. All thresholds are computed deterministically in Python and handed to the model as established facts. The model never decides what counts as unusual — it only decides how to say it.

## What it does
1. Syncs sleep, readiness, and activity scores from the Oura v2 API
2. Stores them as one row per metric per day, with idempotent upserts so repeated syncs never duplicate data
3. Analyzes each day against a rolling 60-day baseline — z-score against your own mean, 7-day change, and pairwise Pearson correlations between metrics
4. Explains the result as a short daily briefing and answers follow-up questions in a chat interface, with the statistical vocabulary deliberately banned from the output.

## Stack
Backend: FastAPI · SQLAlchemy 2.0 · PostgreSQL · Pydantic · httpx · Gemini 2.5 Flash 
Frontend: React 19 · TypeScript · Vite

## Setup
Requirements:
* Python 3.10+
* Node 18+
* PostgreSQL
* Oura personal access token (cloud.ouraring.com)
* Google AI Studio API key

Backend:
```
cd backend
uv sync                      
cp .env.example .env         
uvicorn app.main:app --reload
```
.env:
```
OURA_ACCESS_TOKEN=your_token
GOOGLE_API_KEY=your_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/oura_db
SAMPLE_DATABASE_URL=sqlite:///./sample_oura.db
BASELINE_WINDOW_DAYS=30
```
tables are created on setup. then pull your data:
```
curl -X POST "http://localhost:8000/api/v1/sync?days=30"
```
Frontend:
```
cd frontend
npm install
npm run dev          # http://localhost:5173
```

## Architecture
Oura v2 API
    │  async httpx
    ▼
FastAPI backend ──── SQLAlchemy 2.0 ──── PostgreSQL
    │                                    (daily_metrics)
    │  computed stats as facts
    ▼
Gemini 2.5 Flash  ──── plain-language wording only
    │
    ▼
React + TypeScript frontend (Vite)

## Data Model
daily_metrics
  id          int, pk
  day         date, indexed
  metric      str, indexed     i.e. "sleep_score"
  value       float
  created_at  datetime
