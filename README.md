# PersonaAgent

### Agentic Testing for the Web

**PersonaAgent** is an AI-powered testing platform that deploys autonomous browser agents to explore, interact with, and evaluate web applications from the perspective of real users.

Give PersonaAgent a website, define a persona, and watch the agent navigate the product, complete user flows, uncover failures, and surface behavioral regressions.

> **Test your website through the eyes of your users.**

---

## Core Features

* **Autonomous Browser Agents** — Agents navigate and interact with websites like real users.
* **Persona-Based Testing** — Test experiences from different user perspectives.

---

## Why PersonaAgent?

```text
Unit Tests       → "Does the function work?"
E2E Tests        → "Does the scripted flow work?"
PersonaAgent     → "Can an actual user accomplish their goal?"
```

**PersonaAgent bridges the gap between automated testing and real user behavior.**

## Run the UI

Requires Node.js 22.12+ (Node.js 24 recommended).

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The UI starts in a clearly labeled **Demo workspace** with illustrative results. Use **See it in action** to replay a sample journey, select a different persona to compare outcomes, or export a JSON report. **Switch to live** shows your own runs.

The workspace includes an overview, searchable test history, custom persona creation, experience comparisons, and run details with action reasoning and live browser links. Demo data never creates real browser sessions.

### Connect real agents

Start the existing FastAPI application on port 8000 from the `backend` directory:

```powershell
python -m uvicorn main:app --reload --port 8000
```

The Python environment needs the backend's dependencies (`fastapi`, `uvicorn`, `python-dotenv`, `pydantic`, `playwright`, `steel-sdk`, and `anthropic`). Configure `STEEL_API_KEY` and `CLAUDE_API_KEY` in the backend environment before running agents.

The Vite development server proxies `/api` to `http://127.0.0.1:8000`. The UI uses `GET /personas`, `POST /personas`, `POST /runs`, and `GET /runs/{id}`. Active runs refresh every three seconds. Successful results show the backend's 0–10 score and justification; unsuccessful results and agent errors are shown explicitly.

Run history is saved in this browser's local storage. The backend stores runs and custom personas in memory, so pending runs cannot resume after a backend restart. Sample data is kept separate from live history.

### Build and deployment

```powershell
npm run build
npm run lint
```

Serve the generated `frontend/dist` folder. For production, configure your host to proxy `/api` to the FastAPI server. Alternatively, set `VITE_API_BASE_URL` at build time to your API URL and configure the backend's CORS policy for the frontend origin. The Vite proxy is a development feature. Typography uses Google Fonts with local system-font fallbacks.
