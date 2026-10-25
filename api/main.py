"""Run with python -m uvicorn api.main:app --host 127.0.0.1 --port 8000."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.data import Snapshot
from api.schemas import SimulationRequest
from config import ROOT_DIR


def create_app(snapshot: Snapshot | None = None, static_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.snapshot = snapshot or Snapshot()
        yield

    app = FastAPI(title='Cancer Clock planning API', version='0.8.0', lifespan=lifespan,
        description='Published-data snapshot and precomputed planning sensitivity. No personal waiting-time predictions.')

    @app.middleware('http')
    async def snapshot_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/') and response.status_code == 200:
            response.headers['Cache-Control'] = 'public, max-age=300'
            response.headers['X-Snapshot-Issue'] = request.app.state.snapshot.issue_date
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def data(request: Request) -> Snapshot:
        return request.app.state.snapshot

    def check_code(store: Snapshot, code: str):
        if code not in store.codes:
            raise HTTPException(404, 'Trust is unknown, retired or outside the acute cancer cohort')

    @app.get('/health')
    def health(request: Request):
        store = data(request)
        return dict(status='ok', issue_date=store.issue_date, core_trusts=len(store.codes),
                    snapshot_sha256=store.hashes, precomputed=True)

    @app.get('/api/trusts')
    def trusts(request: Request):
        return data(request).trusts

    @app.get('/api/map')
    def map_timeline(request: Request):
        return data(request).map

    @app.get('/api/trust/{code}/forecast')
    def forecast(code: str, request: Request):
        store = data(request); check_code(store, code)
        return {**store.meta, **store.indexes['forecasts_latest'][code], 'history': store.backlogs[code]}

    @app.get('/api/trust/{code}/bottleneck')
    def bottleneck(code: str, request: Request):
        store = data(request); check_code(store, code)
        return {**store.meta, **store.indexes['bottlenecks'][code]}

    @app.get('/api/trust/{code}/history')
    def history(code: str, request: Request):
        store = data(request); check_code(store, code)
        return store.histories[code]

    @app.get('/api/trust/{code}/decision')
    def decision(code: str, request: Request):
        store = data(request); check_code(store, code)
        return store.decision(code)

    @app.get('/api/backtest')
    def backtest(request: Request):
        store = data(request)
        return dict(**store.meta, model=store.reports['backtest_model'], classifier=store.reports['backtest_classifier'])

    @app.get('/api/national')
    def national(request: Request):
        return data(request).national

    @app.post('/api/simulate')
    def simulate(body: SimulationRequest, request: Request):
        store = data(request); check_code(store, body.org_code)
        trust = store.decision(body.org_code)
        if trust['status'] != 'ready':
            raise HTTPException(409, trust.get('reason', 'This trust has no suitable calibration'))
        try:
            return store.select_experiment(body.org_code, body.scenario, body.stage, body.extra_capacity_pct)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    directory = static_dir or ROOT_DIR / 'web' / 'dist'
    if (directory / 'index.html').is_file():
        app.mount('/', StaticFiles(directory=directory, html=True), name='frontend')
    else:
        @app.get('/')
        def missing_frontend():
            return JSONResponse(status_code=503, content={'detail': 'Frontend build missing. Run npm ci and npm run build in web/.'})
    return app


app = create_app()
