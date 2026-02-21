# MediNotes Pro — SAAS Agent

A full-stack app that turns consultation notes (or uploaded PDFs/images) into AI-generated summaries. Built with Next.js, FastAPI, Clerk, OpenAI, and Postgres. Deployable on AWS (App Runner + ECR) or Vercel.

**Live app (AWS App Runner):** [Healthcare Consultation Assistant — MediNotes Pro](https://6m96uii6va.us-east-1.awsapprunner.com)

---

## STAR — What I Did

| | Meaning | What I did |
|---|--------|------------|
| **S**ituation | The problem or context | Needed an app that takes consultation notes (or files), generates clear summaries and next steps, saves history, and can run in the cloud (e.g. AWS). |
| **T**ask | The goal | Build a simple, secure app: sign-in only (no plan gate), optional premium for a better AI model, streaming summaries, PDF/image upload, and stored consultation history. |
| **A**ction | What I built | Next.js frontend with Clerk auth; FastAPI backend with OpenAI streaming; PDF/image text extraction; Postgres for history; Docker image for AWS (ECR + App Runner). |
| **R**esult | The outcome | One app: sign in → enter notes or upload file → get a live summary → see past summaries. One container runs both UI and API; can deploy to AWS App Runner or use Vercel for frontend. |

---

## Definitions (Simple)

- **Streaming:** The AI sends the summary in small pieces as it writes it, so text appears on screen bit by bit instead of all at once.
- **ECR (Elastic Container Registry):** AWS’s place to store Docker images so services like App Runner can pull and run them.
- **Docker image:** A single package with your app code and dependencies so it runs the same on your machine and in the cloud.
- **Clerk:** A service that handles sign-in and user identity (and optional plans) so we don’t build login/passwords ourselves.
- **JWT:** A token that proves “this request is from user X”; the backend uses it to know who is calling the API.
- **Postgres:** A database used to store consultation history (patient name, date, summary) per user.

---

## What This Project Does

**Frontend (Next.js + React)**  
- Landing page with sign-in and “Go to App”.  
- Product page: patient name, visit date, consultation notes **or** PDF/image upload (max 5MB).  
- Submits to the backend and shows the AI summary as it streams in.  
- “Past summaries” list loaded from the API (saved in Postgres).  
- “Upgrade to Premium” link to a pricing page (Clerk).  
- Only login is required to use the app; no plan gate.

**Backend (FastAPI, `saas/api/server.py`)**  
- **POST /api/consultation:** Accepts notes (or file), calls OpenAI (e.g. gpt-5-nano), streams the summary back.  
- **POST /api/history:** Saves a summary (patient name, date, summary) for the signed-in user.  
- **GET /api/history:** Returns that user’s past summaries.  
- **GET /health:** For AWS App Runner health checks.  
- Serves the built Next.js static files from a `static` folder so one server serves both UI and API.  
- Auth: Clerk JWT; Postgres optional (history returns 503 if DB not configured).

**Deployment**  
- **Docker:** Dockerfile at repo root; build from `saas/` with `-f ../dockerfile`. Multi-stage: Node builds Next.js → Python image gets `out/` as `static` and runs FastAPI on port 8000.  
- **AWS:** Push image to ECR, then create an App Runner service using that image; set env vars (OpenAI, Clerk, optional PostGRES_URL).  
- **Vercel:** Can deploy the Next.js app; backend can be serverless (e.g. `saas/api/index.py`) with consultation and history endpoints.

---

## Project Layout

- **SAAS_Agent/** — Repo root.  
  - **dockerfile** — Builds the app (Next.js + FastAPI) into one image.  
  - **.dockerignore** — Excludes files from the Docker build.  
  - **saas/** — Main app.  
    - **pages/** — Landing (`index`), product (consultation form), pricing.  
    - **api/** — `server.py` (FastAPI for Docker/AWS), `index.py` (for Vercel serverless if used).  
    - **package.json**, **requirements.txt** — Node and Python deps.  
    - **.env** — Local env vars (not committed).  
  - **planning/** — Planning notes.

---

## How to Run Locally

1. **Env vars** (in `saas/.env` or exported in the shell):  
   `OPENAI_API_KEY`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`.  
   Optional: `POSTGRES_URL` or `DATABASE_URL` for history.

2. **Frontend:**  
   `cd saas && npm install && npm run dev`  
   Open http://localhost:3000.

3. **Backend:**  
   From `saas/`, run the FastAPI server (e.g. `uvicorn api.server:app --reload`).  
   For the full “one server” setup, build Next.js (`npm run build`), then serve the `out/` folder as `static` (same as in the Dockerfile).

---

## How to Build and Deploy to AWS

1. **Set env:**  
   `export DEFAULT_AWS_REGION=us-east-1`  
   `export AWS_ACCOUNT_ID=507190177471`  
   `export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_..."`

2. **Build image (from `saas`):**  
   `docker build -f ../dockerfile --platform linux/amd64 --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" -t consultation-app:latest .`

3. **ECR login, tag, push:**  
   `aws ecr get-login-password --region $DEFAULT_AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com`  
   `docker tag consultation-app:latest $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest`  
   `docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest`

4. **App Runner:** Create a service; select ECR repo `consultation-app`, tag `latest`. Add env vars (OpenAI, Clerk, optional Postgres). App listens on port **8000** and exposes **/health**.

---

## How I Deployed on AWS (Step-by-Step) and Auto Scaling

This is how the app was deployed so users can open it on the internet, and how auto scaling is set up.

### 1. Build and push the Docker image to ECR
- **What it does:** ECR is where your container image lives. App Runner pulls the image from here to run your app.
- **What I did:** Built the image from `saas/` with `-f ../dockerfile`, tagged it as `consultation-app:latest`, logged in to ECR, and ran `docker push` to the repository `507190177471.dkr.ecr.us-east-1.amazonaws.com/consultation-app:latest`.

### 2. Create an App Runner service
- **What it does:** App Runner runs your container and gives you a public URL (and optional custom domain). It handles load balancing and scaling.
- **What I did:** In AWS Console → **App Runner** → **Create service**. Chose "Container registry" → **Amazon ECR**. Selected the **consultation-app** repository and tag **latest**. App Runner uses this to run the same image you pushed.

### 3. Configure the service (port, env, health)
- **What it does:** The service must know which port your app uses, which env vars to pass (OpenAI, Clerk, etc.), and how to check if the app is healthy.
- **What I did:** Set **Port** to **8000** (FastAPI listens here). Added **Environment variables** (e.g. `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, optional `POSTGRES_URL`). The app exposes **/health**; App Runner uses it for health checks so it only sends traffic to healthy instances.

### 4. Auto scaling (what it is and how it's set)
- **What it does:** Auto scaling increases or decreases the number of running instances based on traffic. More users → more instances; less traffic → scale down to save cost.
- **What I did:** In the App Runner service configuration, under **Auto scaling** (or "Configure service" → scaling): set **Min size** (e.g. 1 so the app is always available) and **Max size** (e.g. 3 or 5 so it doesn't scale infinitely). Optionally set **Max concurrency** per instance (how many requests one instance handles before scaling out). App Runner then scales within these limits automatically; no separate "auto scaling" service is needed — it's built into App Runner.

### 5. Deploy and get the URL
- **What it does:** App Runner deploys your image and assigns a default domain. That's the link users open in a browser.
- **What I did:** After the service was created and the first deployment finished, I copied the **Default domain** from the App Runner service page. That URL is the one to share with users.

**Live app URL:** [https://6m96uii6va.us-east-1.awsapprunner.com](https://6m96uii6va.us-east-1.awsapprunner.com) — Healthcare Consultation Assistant (MediNotes Pro).

---

## Summary

- **What I did:** Built MediNotes Pro — consultation notes (or PDF/image) in, AI summary out, with login, optional premium, and history stored in Postgres.  
- **STAR:** Situation (need for a cloud-ready summarizer) → Task (secure, streaming app with history) → Action (Next.js + FastAPI + Clerk + OpenAI + Postgres + Docker) → Result (one app, deployable on AWS or Vercel).  
- **Run:** Frontend in `saas` with `npm run dev`; backend via `server.py`; set OpenAI + Clerk (+ optional Postgres).  
- **Deploy AWS:** Build from `saas` with `-f ../dockerfile`, push to ECR, run on App Runner on port 8000 with env vars set.  
- **Live URL:** [https://6m96uii6va.us-east-1.awsapprunner.com](https://6m96uii6va.us-east-1.awsapprunner.com)
