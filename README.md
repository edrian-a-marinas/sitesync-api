# SiteSync — Construction Project & Daily Site Log SaaS

## Plain English Concept

**What users do:** Create and manage construction projects, then for each project log daily site activity — workers present, materials consumed, equipment used, and incidents if any. Project Managers submit end-of-shift logs from their assigned site, Project Managers monitor all their projects from a centralized dashboard, and the Owner gets a full cross-project view with an AI assistant that answers questions about cost, progress, materials, workforce, and project performance across all historical records.

**Scope:** Designed for civil engineering and construction companies managing multiple active projects such as residential buildings, commercial developments, roads, bridges, and infrastructure works. The platform focuses on project oversight, daily site operations, workforce tracking, material consumption monitoring, and progress reporting across all construction phases.

**Purpose:** Construction firms running multiple simultaneous projects often lose visibility into daily progress, material consumption, equipment usage, and worker attendance because information is scattered across paper logs, spreadsheets, messaging groups, and disconnected systems. This provides a centralized daily site logging platform where every project submits structured end-of-shift reports, transforming fragmented field data into a single AI-queryable command center that enables leadership to monitor operations and make decisions without manually reviewing spreadsheets or reports.

---

## Full Technical Concept

### AWS Services

| AWS Service | Description |
|------------|-------------|
| **S3** | Stores photos, documents, and generated reports. |
| **EC2** | Hosts the FastAPI application and background workers celery.  |
| **RDS** | PostgreSQL database for all project, user, and site log data. |
| **ALB** | Distributes traffic across multiple EC2 instances. |

### Authentication & User Layer

Users register and authenticate via JWT-based auth built into FastAPI. All resources — projects, site assignments, daily logs, attendance records, material entries, reports, and AI query history — are scoped per authenticated user and role. Three roles exist: Owner (full access, cross-project visibility, AI queries, and reporting), Project Manager (assigned projects only with full log management capabilities), and Site Worker (attendance submission and site-level reporting for assigned locations only). AWS IAM manages backend cloud credentials for S3 and RDS access, enforcing least-privilege permissions at the infrastructure layer.

### Project & Site Management

Owners create projects with a name, location, budget, start date, and target completion date. Each project contains multiple phases such as Foundation, Structure, and Finishing, with budget allocations and progress tracking maintained separately for each phase. Project Managers are assigned to projects by the Owner, while Site Workers are assigned to specific sites under those projects. All project records are represented as SQLAlchemy models stored in AWS RDS PostgreSQL. Alembic manages schema migrations for projects, phases, assignments, and related project management tables.

### Daily Site Log

Each end-of-shift log is stored as a SQLAlchemy model in RDS PostgreSQL and contains the project reference, submitting Project Manager, reporting date, workers present with hours worked, materials consumed with quantities and unit costs, equipment deployed, weather conditions, work accomplished, incident reports, and submission timestamps. Project Managers submit attendance on behalf of their assigned workers during end-of-shift logging. Site Workers can view their own attendance history but do not submit attendance directly. Alembic manages all schema versioning for logs, attendance records, equipment usage, and material tracking tables.

### File Storage

Project Managers upload supporting documentation for daily logs including progress photos, material delivery receipts, inspection documents, and incident evidence. Files are stored as objects in AWS S3 via boto3, keeping binary data entirely outside the relational database. PostgreSQL stores only metadata such as filename, upload date, associated log reference, file type, and S3 object key through SQLAlchemy models. Alembic manages schema migrations for file and photo metadata tables.

### Background Report Generation

When a weekly progress report is requested — either manually by a Project Manager or automatically every Monday through Celery Beat — the FastAPI API submits a report-generation task to a Celery worker using Redis as the message broker so the request can return immediately. The worker aggregates all project activity for the reporting period, including workforce statistics, labor hours, material costs, equipment utilization, incidents, and completed work summaries. A structured PDF report is generated, uploaded to AWS S3, and the report metadata is written back to PostgreSQL upon completion. Owners and Project Managers can access historical reports through signed URL endpoints.

### AI Query Layer — RAG

When an Owner submits a natural language question such as "Which project consumed the most cement this month?", "Which site had the most incidents this quarter?", or "Which phase is currently most over budget?", the FastAPI endpoint forwards the request to a Celery worker through Redis. The worker retrieves relevant structured context from PostgreSQL including project budgets, attendance records, material consumption logs, daily reports, incident records, and generated reports. The worker assembles the final prompt and calls the LLM to generate a direct, data-grounded answer. Queries and responses are stored per user for historical reference.

### ML Analytics & Predictive Insights

SiteSync runs a dedicated ML pipeline that trains predictive models on accumulated project data, serving the Owner exclusively. A budget overrun classifier, delay risk scorer, and material demand forecaster are trained on historical logs, attendance, material consumption, and budget actuals from RDS PostgreSQL — retrained automatically every week via Celery Beat. Predictive insights are served via dedicated ML endpoints — budget overrun probability, delay risk score, and material cost forecast — accessible exclusively by the Owner through a dedicated Analytics page in the frontend. This page is separate from the operational Dashboard and historical Reports, giving leadership a focused forward-looking view of project risk and material demand.

### Caching

Redis stores frequently accessed responses including project lists, dashboard KPIs, attendance summaries, material consumption statistics, budget reports, and AI query metadata. Cached responses use TTL expiration together with mutation-based invalidation strategies. React Query manages client-side cache synchronization, ensuring stale data is automatically revalidated after any project update, assignment change, daily log submission, attendance update, or report generation event without requiring manual refreshes.

### Dashboard & KPIs

The Owner dashboard provides organization-wide visibility across all active projects, displaying total active projects, budget versus actual spending, workforce activity, project health indicators, over-budget alerts, schedule delays, and company-wide material consumption trends. The Project Manager dashboard focuses on assigned projects and displays daily log completion status, budget utilization by phase, attendance rates, material usage trends, incident tracking, and project productivity metrics. All KPI data is Redis-cached and automatically invalidated whenever new site activity is recorded.

### Storage & Hosting

FastAPI, Celery workers, and Redis are containerized with Docker and orchestrated locally through docker-compose during development. The production environment runs on AWS EC2. Site photos, uploaded documents, and generated PDF reports are stored in AWS S3, while all relational data is stored in AWS RDS PostgreSQL. Redis serves both as the caching layer and Celery message broker. After load testing with Locust identifies single-instance bottlenecks under approximately 500 concurrent users, an AWS Application Load Balancer (ALB) is placed in front of multiple EC2 instances to provide horizontal scaling and high availability.

GitHub Actions runs the full Pytest and pytest-asyncio test suite on every push, covering API endpoints, Celery tasks, role-based access control, AI query validation, database operations, report generation workflows, and file upload functionality. Failed tests block deployment and prevent broken code from reaching production.

### Frontend

Next.js with TypeScript handles routing, page rendering, and application layouts. TailwindCSS builds the responsive user interface. Zod validates all client-side inputs including project creation forms, attendance records, daily site logs, material consumption entries, equipment usage records, and user assignments before requests reach the backend. React Query manages asynchronous data fetching, caching, and server-state synchronization with the FastAPI backend.

UI/UX for roles
All three roles share the same UI shell — same sidebar, same navigation structure, same dashboard layout — but what each role sees inside it is gated by their role. The Owner sees all projects, the AI query panel, and the ML Analytics dashboard, the Project Manager sees only their assigned projects, and the The Site Worker sees only their assigned project, their own attendance history, and the daily log for their current shift — same interface, different world inside it. — same interface, different world inside it.

### Role Based-Access Control 

Owner — the construction company owner/CEO. The person who runs the business, owns all projects, sees everything, uses the AI assistant to make decisions. Not necessarily technical — just the boss.
Project Manager — in construction this is typically the Civil Engineer or Site Engineer or Site Manager or Foreman. They manage the full project lifecycle, submit daily logs, monitor budget vs actual, assign workers. Could also be a Foreman in smaller firms.
Site Worker — the construction workers on the ground. Masons, carpenters, electricians, laborers. They just log attendance and see their daily tasks. No management access.

### Owner & Project Manager Panel
Owner and Project Manager share the same UI shell and sidebar. The backend enforces data scoping per role — Owners see all projects, Managers see only assigned ones. Analytics and AI Assistant are hidden from Project Managers since their backend endpoints are owner-only.

| Menu | Description | Owner | Project Manager |
|------|-------------|-------|-----------------|
| **Dashboard** | KPIs scoped per role — budget, workforce, incidents, project health. | ✅ | ✅ |
| **Projects** | Project and phase management. Managers get view-only on assigned projects. | ✅ | ✅ |
| **Daily Logs** | Submit and manage daily site logs. | ✅ | ✅ |
| **Reports** | Weekly PDF reports. Scoped per role. | ✅ | ✅ |
| **Analytics** | ML predictions — budget overrun, delay risk, material forecast. | ✅ | ❌ |
| **AI Assistant** | Natural language query interface for cross-project insights. | ✅ | ❌ |

### Site Worker Panel
Separate minimal UI — same design system, different shell and nav.

| Menu | Description |
|------|-------------|
| **My Attendance** | View personal attendance history across assigned projects. |
| **Daily Log** | View the current shift daily log for their assigned project. |