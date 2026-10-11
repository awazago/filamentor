from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles

from . import __doc__ as tagline
from .analysis import AnalysisError, analyze
from .catalog import SUPPORTED_MATERIALS, CatalogError, get_catalog

MAX_UPLOAD_BYTES = 250 * 1024 * 1024

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Filamentor", description=tagline, version="0.1.0")


def _catalog():
    try:
        return get_catalog()
    except CatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    try:
        get_catalog()
    except CatalogError as exc:
        return {"status": "degraded", "catalog": str(exc)}
    return {"status": "ok", "catalog": "ok"}


@app.get("/api/printers")
def printers():
    return [asdict(p) for p in _catalog().printers()]


@app.get("/api/materials")
def materials():
    return list(SUPPORTED_MATERIALS)


@app.get("/api/processes")
def processes(machine: str = Query(..., description="Preset da impressora")):
    try:
        return [asdict(p) for p in _catalog().processes(machine)]
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/filaments")
def filaments(
    machine: str = Query(..., description="Preset da impressora"),
    material: str | None = Query(None, description="PLA, PETG ou TPU"),
):
    if material and material not in SUPPORTED_MATERIALS:
        raise HTTPException(status_code=422, detail=f"Material não suportado: {material}")
    try:
        return [asdict(f) for f in _catalog().filaments(machine, material)]
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/presets/resolved")
def resolved_preset(name: str = Query(..., description="Nome exato do preset")):
    """Preset achatado (herança resolvida). Útil para depuração e para o CLI do Bambu Studio."""
    try:
        return _catalog().library.resolve(name)
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/analyze")
def analyze_model(file: UploadFile):
    """Análise geométrica. Síncrono de propósito: o FastAPI roda em threadpool e o
    trabalho é CPU-bound (numpy/embree)."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo maior que 250 MB")
    try:
        return asdict(analyze(data, file.filename or "", _catalog().printers()))
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Montado por último para não encobrir as rotas /api.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
