sequenceDiagram
    participant U as User
    participant F as Frontend (Next.js)
    participant C as Clerk
    participant B as Backend (FastAPI)
    participant O as OpenAI

    U->>F: Sign in
    F->>C: Auth
    C->>F: JWT
    U->>F: Submit form (notes / file)
    F->>F: getToken()
    F->>B: POST /api/consultation + JWT
    B->>C: Verify JWT (JWKS)
    C-->>B: Valid
    B->>B: Resolve notes (or extract from file)
    B->>O: Chat completions (stream)
    O-->>B: Stream chunks
    B-->>F: SSE stream
    F-->>U: Show summary text
    F->>B: POST /api/history (save)
    B->>B: Save to Postgres# MediNotes Pro — SAAS Agent

**Healthcare Consultation Assistant** that turns your consultation notes (or uploaded PDFs and images) into clear AI-generated summaries, action items, and follow-ups. One app: sign in, add notes or a file, get a live summary, and see your past summaries.

**Try it live:** [https://6m96uii6va.us-east-1.awsapprunner.com](https://6m96uii6va.us-east-1.awsapprunner.com)

---

## STAR — What This Project Is (Start to End)

STAR stands for **Situation → Task → Action → Result**. Here’s the full story in simple language.

### Situation (The Problem)

Healthcare workers need to turn messy consultation notes into clear, structured summaries and next steps. Doing this by hand is slow and inconsistent. We also needed:

- A way to use **typed notes or uploaded files** (PDFs, images).
- **Summaries that stream** so users see text as it’s generated.
- **Saved history** so past consultations can be reviewed.
- The app to run **in the cloud** (e.g. AWS) so anyone with a link can use it.

### Task (The Goal)

Build a single, easy-to-use app where:

- Users **sign in once** (no blocking “premium only” gate — everyone can use it after login).
- They enter **patient name**, **visit date**, and either **type notes** or **upload a PDF/image** (up to 5MB).
- The app calls an **AI** to generate a summary and streams it **live** on the page.
- Summaries are **saved** and listed under “Past summaries.”
- **Premium** users can get a better AI model; others see “Upgrade to Premium” but still use the app.

### Action (What Was Built)

| Part | What it is | What it does |
|------|------------|--------------|
| **Frontend** | Next.js + React | Landing page, sign-in, consultation form (notes or file), streaming summary view, past summaries list, pricing/upgrade link. |
| **Auth** | Clerk | Sign-in and user identity; backend trusts the user via a JWT token. |
| **Backend** | FastAPI (Python) | Receives notes (or file), extracts text from PDFs/images if needed, calls OpenAI, streams the summary back; saves/loads history. |
| **AI** | OpenAI | Generates the consultation summary (e.g. gpt-5-nano). |
| **Database** | Postgres (optional) | Stores consultation history (patient name, date, summary) per user. |
| **Deployment** | Docker + AWS | One Docker image (frontend + backend); pushed to ECR; run on App Runner with auto scaling. |

**Process in one sentence:** User signs in (Clerk) → fills the form or uploads a file → frontend sends it to the backend with a JWT → backend gets notes (or extracts text from file), calls OpenAI, streams the reply → frontend shows the stream and then saves the summary to Postgres via the API → user can open “Past summaries” anytime.

### Result (The Outcome)

- **One app:** Sign in → enter notes or upload file → see a live summary → view past summaries. No separate “admin” or “doctor” app.
- **One deployment:** A single Docker image serves both the web UI and the API. On AWS, App Runner runs it and scales automatically.
- **One URL for users:** The link above is the live app; share it so others can use it.

---

## Key Terms (Reader-Friendly)

- **Streaming:** The AI sends the summary in small chunks. You see text appear bit by bit instead of waiting for the whole answer at once.
- **ECR (Elastic Container Registry):** AWS’s storage for Docker images. App Runner pulls the image from here to run your app.
- **Docker image:** A single package containing your app and its dependencies so it runs the same on your laptop and in the cloud.
- **Clerk:** A service that handles sign-in and user identity (and optional subscription plans). We don’t build passwords or login pages ourselves.
- **JWT:** A token that proves “this request is from user X.” The backend uses it to know who is calling the API.
- **Postgres:** A database. Here it stores consultation history (who, when, and the summary) per user.
- **App Runner:** An AWS service that runs your Docker image, gives you a public URL, and scales the number of instances up or down with traffic (auto scaling).
- **Auto scaling:** The number of running instances increases when there’s more traffic and decreases when it’s quiet, so the app stays responsive without overpaying.

---

## End-to-End Process (What Happens When Someone Uses the App)

### User journey (what the user sees)

1. Opens the **live link** (or your own deployment).
2. Lands on the **MediNotes Pro** page; clicks **Sign In** and completes sign-in (Clerk).
3. Clicks **Go to App** (or similar) and reaches the **Consultation** page.
4. Enters **patient name**, **visit date**, and either **types notes** or **uploads a PDF/image**.
5. Clicks **Submit**. The **summary appears line by line** (streaming) as the AI writes it.
6. When done, the summary is **saved** and appears under **Past summaries**. They can click any past summary to view it again.
7. If they’re not premium, they see **Upgrade to Premium**; they can still use the app.

### Technical flow (what the system does)

1. **Frontend** (Next.js): Renders the form; when the user submits, it gets a **JWT** from Clerk and sends a request to **POST /api/consultation** with the JWT, patient name, date, and notes (or base64 file + mime type).
2. **Backend** (FastAPI): Checks the JWT (Clerk). If there’s a file, it **extracts text** (PDF or image via OpenAI vision). It builds a prompt and calls **OpenAI** with streaming.
3. **Backend** sends the reply as **Server-Sent Events** (SSE); the **frontend** uses `fetchEventSource` to read chunks and update the screen in real time.
4. When the stream **ends**, the frontend calls **POST /api/history** with the final summary; the backend saves it to **Postgres** (if configured) under the user’s ID.
5. **GET /api/history** (with JWT) returns that user’s past summaries so the “Past summaries” list can be filled.

Everything the user sees (pages, form, streaming text, history) is served by the **same app**: the backend serves the built Next.js static files and the API from one server (e.g. port 8000).

---

## Project Structure (Where Everything Lives)

```
SAAS_Agent/
├── README.md              ← You are here
├── dockerfile             ← Builds the full app (Next.js + FastAPI) into one Docker image
├── .dockerignore          ← Tells Docker which files to skip when building
└── saas/                  ← Main application
    ├── pages/             ← Next.js pages
    │   ├── index.tsx      ← Landing (MediNotes Pro, Sign In, Go to App)
    │   ├── product.tsx    ← Consultation form, streaming summary, past summaries
    │   └── pricing.tsx    ← Upgrade / pricing (Clerk)
    ├── api/
    │   ├── server.py      ← FastAPI app for Docker/AWS (consultation, history, health, static files)
    │   └── index.py       ← Optional: serverless entry for Vercel
    ├── package.json       ← Node/Next.js dependencies
    ├── requirements.txt   ← Python dependencies (FastAPI, OpenAI, Clerk auth, Postgres, etc.)
    └── .env               ← Local env vars (not committed; you create this)
```

- The **frontend** is built with `npm run build`; Next.js outputs static files into `out/`. The Dockerfile copies `out/` as `static` so the backend can serve them.
- The **backend** is `api/server.py`: it mounts the static folder, defines `/api/consultation`, `/api/history`, and `/health`, and runs with `uvicorn` on port 8000.

---

## How to Run Locally (Step by Step)

1. **Get the code**  
   Clone the repo and open a terminal in the project root.

2. **Create env vars**  
   In the `saas/` folder, create a `.env` file (or export these in your shell). You need:
   - `OPENAI_API_KEY` — from OpenAI (required for summaries).
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` — from Clerk (starts with `pk_`).
   - `CLERK_SECRET_KEY` — from Clerk (starts with `sk_`).
   - `CLERK_JWKS_URL` — from Clerk (e.g. `https://….clerk.accounts.dev/.well-known/jwks.json`).  
   Optional (for history): `POSTGRES_URL` or `DATABASE_URL`.

3. **Install and run the frontend**  
   From `saas/`: run `npm install`, then `npm run dev`. Open http://localhost:3000. You’ll see the landing page; sign-in and “Go to App” will work only if the backend is running and the frontend is configured to call it (same origin or correct API URL).

4. **Run the backend**  
   From `saas/`, run the FastAPI server, e.g. `uvicorn api.server:app --reload --host 0.0.0.0 --port 8000`. For the “one server” setup (like production), build the frontend (`npm run build`), then serve the `out/` folder as `static` so the same process serves both the UI and the API.

5. **Use the app**  
   Sign in, go to the product page, enter notes or upload a file, and submit. You should see the summary stream in. Past summaries work if Postgres is configured.

---

## How to Deploy to AWS (Step-by-Step, With Explanations)

This is how the live app was put on the internet and how auto scaling is set.

### Step 1: Build the Docker image

- **Why:** The app must run in a container that includes both the built frontend and the Python backend.
- **What you do:** From the `saas/` folder, run the build with the Dockerfile in the parent folder. Pass the Clerk publishable key so the frontend is built with the right auth config.
- **Command (from `saas/`):**
  ```bash
  export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_..."
  docker build -f ../dockerfile --platform linux/amd64 \
    --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
    -t consultation-app:latest .
  ```
- **What it does:** The Dockerfile first builds the Next.js app (Node), then copies the built files into a Python image and installs dependencies. The result is one image tagged `consultation-app:latest`.

### Step 2: Push the image to ECR

- **Why:** App Runner doesn’t build your code; it runs an image that you store in ECR.
- **What you do:** Log in to ECR, tag the image with your ECR repository URL, then push.
- **Commands (set your region and account ID first):**
  ```bash
  export DEFAULT_AWS_REGION=us-east-1
  export AWS_ACCOUNT_ID=507190177471
  aws ecr get-login-password --region $DEFAULT_AWS_REGION | \
    docker login --username AWS --password-stdin \
    $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com
  docker tag consultation-app:latest \
    $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest
  docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest
  ```
- **What it does:** ECR is like a registry for your Docker images. After this, App Runner can pull `consultation-app:latest` from your account.

### Step 3: Create an App Runner service

- **Why:** App Runner is the service that runs your container and gives you a public URL.
- **What you do:** In the AWS Console, go to **App Runner** → **Create service**. Choose **Container registry** → **Amazon ECR**, then select the **consultation-app** repository and tag **latest**.
- **What it does:** App Runner will run your image and later assign a default domain (e.g. `https://xxxxx.us-east-1.awsapprunner.com`).

### Step 4: Configure port, environment, and health

- **Why:** The service must know which port your app uses, which secrets to pass in, and how to check that the app is healthy.
- **What you do:** Set **Port** to **8000**. Add **Environment variables** (e.g. `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, and optionally `POSTGRES_URL`). The app exposes **GET /health**; App Runner uses it to decide if an instance is healthy.
- **What it does:** Traffic is sent to port 8000; your app gets the env vars it needs; unhealthy instances are replaced.

### Step 5: Set auto scaling

- **Why:** So the app can handle more users when traffic goes up and scale down when it’s quiet.
- **What you do:** In the App Runner service configuration, under **Auto scaling**, set **Min size** (e.g. 1) and **Max size** (e.g. 3 or 5). Optionally set **Max concurrency** per instance.
- **What it does:** App Runner increases or decreases the number of instances within these limits. No separate “auto scaling” service is needed; it’s built into App Runner.

### Step 6: Deploy and get the URL

- **Why:** You need a link to give to users.
- **What you do:** After the first deployment finishes, open the App Runner service in the console and copy the **Default domain**.
- **What it does:** That URL (e.g. https://6m96uii6va.us-east-1.awsapprunner.com) is the live app. Share it with users.

**Live app URL:** [https://6m96uii6va.us-east-1.awsapprunner.com](https://6m96uii6va.us-east-1.awsapprunner.com) — Healthcare Consultation Assistant (MediNotes Pro).

---

## Summary (Quick Reference)

- **What this is:** MediNotes Pro — consultation notes or PDF/image in → AI summary out, with sign-in, optional premium, and saved history.
- **STAR:** **S**ituation (need for a cloud-ready consultation summarizer) → **T**ask (secure app with streaming and history) → **A**ction (Next.js + FastAPI + Clerk + OpenAI + Postgres + Docker) → **R**esult (one app, one URL, deployable on AWS).
- **Run locally:** Set env vars in `saas/`, run `npm run dev` and the FastAPI server (e.g. `uvicorn api.server:app --reload`); optional Postgres for history.
- **Deploy to AWS:** Build image from `saas/` with `-f ../dockerfile`, push to ECR, create an App Runner service (port 8000, env vars, auto scaling), then use the default domain as the live URL.
- **Live URL:** [https://6m96uii6va.us-east-1.awsapprunner.com](https://6m96uii6va.us-east-1.awsapprunner.com)
