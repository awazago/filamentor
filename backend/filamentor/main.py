import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.staticfiles import StaticFiles

from . import __doc__ as tagline
from .analysis import AnalysisError, analyze, load_mesh, prepare_mesh
from .catalog import SUPPORTED_MATERIALS, CatalogError, get_catalog

MAX_UPLOAD_BYTES = 250 * 1024 * 1024
# Uploads ficam só em memória, para trocar de placa e servir a malha ao visualizador sem
# reenviar o arquivo. Nada é gravado em disco; os mais antigos saem primeiro.
MAX_CACHED_UPLOADS = 4

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


_uploads: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
_uploads_lock = threading.Lock()


def _remember(data: bytes, filename: str) -> str:
    upload_id = uuid.uuid4().hex
    with _uploads_lock:
        _uploads[upload_id] = (data, filename)
        while len(_uploads) > MAX_CACHED_UPLOADS:
            _uploads.popitem(last=False)
    return upload_id


def _recall(upload_id: str) -> tuple[bytes, str]:
    with _uploads_lock:
        if upload_id not in _uploads:
            raise HTTPException(status_code=404, detail="Upload expirado: envie o arquivo de novo")
        _uploads.move_to_end(upload_id)
        return _uploads[upload_id]


def _analysis(data: bytes, filename: str, plate: int | None, upload_id: str) -> dict:
    try:
        result = asdict(analyze(data, filename, _catalog().printers(), plate))
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "upload_id": upload_id}


# Endpoints síncronos de propósito: o FastAPI os roda em threadpool e o trabalho é
# CPU-bound (numpy/embree).
@app.post("/api/analyze")
def analyze_model(file: UploadFile, plate: int | None = Query(None, ge=1)):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo maior que 250 MB")
    filename = file.filename or ""
    result = _analysis(data, filename, plate, upload_id="")
    result["upload_id"] = _remember(data, filename)
    return result


@app.get("/api/uploads/{upload_id}/analysis")
def upload_analysis(upload_id: str, plate: int | None = Query(None, ge=1)):
    data, filename = _recall(upload_id)
    return _analysis(data, filename, plate, upload_id)


@app.get("/api/uploads/{upload_id}/mesh")
def upload_mesh(upload_id: str, plate: int | None = Query(None, ge=1)):
    """Malha analisada (sem fragmentos, apoiada na mesa) em STL binário, para o visualizador."""
    data, filename = _recall(upload_id)
    try:
        mesh, _, _ = prepare_mesh(load_mesh(data, filename, plate))
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=mesh.export(file_type="stl"), media_type="model/stl")


# Montado por último para não encobrir as rotas /api.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
