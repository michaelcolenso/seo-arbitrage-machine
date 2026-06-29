# datasiteforge-api

The **Phase 8** control plane: a FastAPI gateway that exposes the full
DataSiteForge lifecycle as REST endpoints, backed by a background thread-pool job
worker, plus a self-contained operator console.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Liveness + version |
| GET | `/fleet/status` | Ledger state counts across every lifecycle stage |
| GET | `/analytics/revenue` | Revenue + traffic scorecard |
| GET | `/opportunities` `/evaluations` `/deployments` `/optimizations` | Ledger listings |
| POST | `/scout/run` | Start a scouting pass (background job) |
| POST | `/evaluate/run` | Evaluate pending opportunities |
| POST | `/compile/run` | Compile an approved evaluation |
| POST | `/deploy/run` | Deploy a completed site generation |
| POST | `/optimize/run` | Run the telemetry + reinforcement loop |
| GET | `/jobs` `/jobs/{id}` | Poll background job state |
| GET | `/` | Operator console (single-page, Tailwind + Alpine) |

Long-running lifecycle actions are submitted to an in-process thread-pool worker
and return a `job_id`; poll `/jobs/{id}` for `queued → running → succeeded/failed`
and the orchestrator's structured report.

## Run

```
seo-platform serve            # uvicorn on http://127.0.0.1:8000
# or
uvicorn dsf_api.app:create_app --factory
```
