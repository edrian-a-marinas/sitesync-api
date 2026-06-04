# ApplyLens — AI Resume-to-Job Fit Analyzer & Application Tracker

## Plain English Concept

**What users do:** Save one or more personal resumes, then for each job opportunity input a company name, job position, job description, and optionally a job posting URL and the platform they found it on (JobStreet, Indeed, LinkedIn, etc.). They receive an honest AI verdict with a 1–10 alignment score, matched skills, gaps, and improvement suggestions — or toggle to generate a tailored cover letter instead. Every analysis lives in one of two sections: Saved (not yet applied) or Applied (submitted), each with its own view and ordering.

**Purpose:** Job hunters apply blindly across dozens of companies and platforms and lose track of where everything stands — this gives them an honest pre-application audit with a clear alignment score so they prioritize the right applications first. The split between Saved and Applied, platform tagging, status tracking, and clickable job post links turn a chaotic multi-platform job hunt into one organized, data-informed command center.

---

## Full Technical Concept

### Authentication & User Layer

Users register and authenticate via JWT-based auth built into FastAPI. All resources — resumes, analyses, application records — are scoped per authenticated user. AWS IAM manages the backend's cloud credentials for S3 and RDS access, enforcing least-privilege access keys at the application layer.

### Resume Storage

Users upload resume files (PDF) through a FastAPI endpoint. Files are stored as objects in AWS S3 via boto3, keeping binary files out of the database entirely. The PostgreSQL database on AWS RDS stores only the resume metadata — filename, label, upload date, S3 object key — as a SQLAlchemy model. Users can save multiple resumes with custom labels (e.g., "Resume v1 - General", "Resume v2 - Backend Focus"). Alembic manages all schema migrations for the resumes table.

### Job Application Record

Each application record is a SQLAlchemy model stored in RDS PostgreSQL containing: company name, job position, job description (text), optional job posting URL, optional platform source (JobStreet, Indeed, LinkedIn, etc.), AI verdict output, alignment score (1–10), generated cover letter (if requested), status (Saved / Applied / Interviewing / Rejected / Offer), pinned flag, and timestamps. Alembic handles all schema versioning for this table.

### AI Analysis Flow

When a user submits a job for analysis, the FastAPI endpoint validates all inputs via Pydantic, then pushes the heavy AI task to a Celery worker through Redis as the message broker — so the API responds immediately without waiting for the LLM. The Celery worker retrieves the relevant resume(s) from S3, assembles the full prompt context (resume content + job description + position + company), and calls the LLM to return a structured verdict: alignment score 1–10, matched skills, skill gaps, honest assessment, and improvement suggestions.

If cover letter mode is toggled, the worker instead prompts the LLM to generate a tailored cover letter for that specific job description and position. The structured AI output is written back to the application record in RDS on task completion. MCP exposes this backend data pipeline as a secure, open-standard interface connecting the custom backend context to AI client ecosystems.

### Auto Resume Selector

If the user submits a job analysis without selecting a specific resume, the Celery worker retrieves all of the user's saved resumes from S3, sends them together with the job description to the LLM, and prompts it to identify the best-matching resume before running the full analysis on it. The selected resume label is stored on the record so the user knows which one was used.

### Caching

Redis cache stores frequently accessed responses — resume lists, application record lists, dashboard stats — with TTL and invalidation on mutation. React Query on the frontend manages client-side cache sync, ensuring stale data is automatically revalidated after any create, update, or status change without requiring manual refreshes.

### Application Pipeline — Two Sections

Records default to Saved on creation. The user manually moves a record to Applied when they submit the real application. The Saved section is an unordered backlog. The Applied section is an ordered pipeline sorted by: pinned records first, then descending alignment score, then most recent.

This gives the user an instant priority view of their strongest active applications at the top. Platform source tags (JobStreet, Indeed, etc.) are filterable so users can see how many applications they've sent per platform.

### Storage & Hosting

FastAPI, Celery workers, and Redis are containerized with Docker and orchestrated locally via docker-compose for development. The live application runs on AWS EC2. Resume files live in AWS S3. All persistent relational data lives in AWS RDS PostgreSQL.

GitHub Actions runs the full Pytest + pytest-asyncio test suite on every push, covering endpoint tests, Celery task tests, AI output validation, role enforcement, and database operations, blocking any broken builds from merging.

### Frontend

Next.js with TypeScript handles all routing, page rendering, and UI layouts. TailwindCSS builds the responsive interface. Zod validates all form inputs client-side before any request reaches the backend. React Query manages all async data fetching, caching, and server state sync with the FastAPI layer.
