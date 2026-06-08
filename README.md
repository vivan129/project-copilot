# project-copilot

AI-powered project planner for students, makers, and robotics enthusiasts.

## Rename this project in one command

```bash
bash rename.sh <your-new-name>
# Example:
bash rename.sh buildmate
```

## Structure

```
project-copilot/
├── frontend/        # Next.js 14 + TypeScript + Tailwind
├── backend/         # FastAPI + PostgreSQL + ChromaDB
├── rename.sh        # Rename everything in one command
└── README.md
```

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in your keys
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local    # fill in your keys
npm run dev
```

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14, TypeScript, TailwindCSS, shadcn/ui |
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL |
| Vector DB | ChromaDB |
| Cache/Queue | Redis + Celery |
| Auth | JWT + Google OAuth |
| AI | OpenAI GPT-4o + RAG |
| Payments | Stripe |
| Hosting | Vercel (frontend) + Railway (backend) |
