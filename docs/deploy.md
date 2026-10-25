# Put the bundled app online

The current ZIP includes the compiled frontend and precomputed data. No Node
build, API key, model training or simulator run is needed during deployment.

On Render, connect the GitHub repository and create a **Web Service**:

| Setting | Value |
| --- | --- |
| Language | Python 3 |
| Branch | The branch containing this update, normally `main` |
| Root directory | Leave blank when `api/` and `requirements-web.txt` are at the repository root |
| Build command | `pip install -r requirements-web.txt` |
| Start command | `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health` |
| Python version | `.python-version` pins the tested 3.12.14 runtime |

Use one worker. In this environment, startup and an all-hospital/API check
peaked at about 371 MiB. This is not a load test or a guarantee for concurrent
traffic. Render's free service is suitable to try for a demo; it sleeps after
15 minutes without traffic and can take about a minute to wake. Open the site
before recording. A paid instance avoids the free-tier sleep.

Official instructions: https://render.com/docs/deploy-fastapi
Free-service limits: https://render.com/docs/free

After deploying, open the assigned URL, search Oxford and test strike +10%
treatment. The 12-week displayed result should be **176 → 148**. `/health`
should return `status: ok`. Later pushes to the connected branch can redeploy.

For local recording: `.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000`.
