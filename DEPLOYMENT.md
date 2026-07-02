# Deployment

Recommended layout:

- GitHub private repository: source code shared by the company PC and Mac
- Vercel: React frontend from `frontend/`
- Render: FastAPI backend from the repository root
- Central database: add Supabase when alloy records must be edited from both local and web

## 1. GitHub

Keep the repository private. Do not commit `.env`, `.env.local`,
`gemini_api_key.txt`, favorites files, caches, or generated frontend files.

On the Mac:

```bash
git clone <private-repository-url>
cd test7
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend
npm ci
```

## 2. Render API

Create a Render Blueprint from the GitHub repository. Render reads
`render.yaml` and builds the root `Dockerfile`.

Add secrets in the Render dashboard, never in Git:

- `GEMINI_API_KEY` when Gemini features are required
- `CEREBRAS_API_KEY` when Cerebras features are required

The health endpoint is `/api/about`.

## 3. Vercel frontend

Import the same GitHub repository into Vercel and configure:

- Root Directory: `frontend`
- Framework: Vite
- Environment variable: `VITE_API_BASE_URL=https://<render-service>.onrender.com`

Redeploy after setting the API URL.

## 4. Local development

Windows keeps the existing workflow:

```text
start_all.bat
```

The local build leaves `VITE_API_BASE_URL` empty, so API calls remain on
`http://localhost:8000`.

## Data synchronization

The current alloy database is source-controlled Python data. Company PC and
Mac changes stay synchronized through GitHub commits, but the running website
cannot edit that database yet.

For web and local editing of the same records, migrate mutable alloy records
and favorites to one Supabase PostgreSQL database. Keep prediction code in Git
and use Supabase as the single data source.
