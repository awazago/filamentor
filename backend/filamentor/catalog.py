"""Catálogo de presets oficiais do Bambu Studio para Bambu Lab A1 e A1 mini.

Os presets do Bambu Studio formam cadeias de herança: cada arquivo declara `inherits`
(o pai) e, opcionalmente, `include` (templates mesclados, ex. G-code de início). O valor
efetivo de uma chave é o do preset mais próximo da folha que a define. O CLI do Bambu
Studio não resolve corretamente essa cadeia para filamentos passados por arquivo, então
o Filamentor sempre trabalha com presets "achatados" (ver `PresetLibrary.resolve`).
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings

PRESET_KINDS = ("machine", "process", "filament")

SUPPORTED_PRINTER_MODELS = {"Bambu Lab A1": "A1", "Bambu Lab A1 mini": "A1M"}
SUPPORTED_MATERIALS = ("PLA", "PETG", "TPU")
# `filament_type` do Bambu Studio -> família de material do Filamentor.
# TPU-AMS é o TPU mais rígido que passa pelo AMS / AMS Lite; PLA-AERO é o PLA espumante.
MATERIAL_FAMILIES = {
    "PLA": "PLA",
    "PLA-AERO": "PLA",
    "PETG": "PETG",
    "TPU": "TPU",
    "TPU-AMS": "TPU",
}

# Dureza do bico de aço inox padrão. Filamentos que exigem mais (CF/GF, ~40 HRC) ficam de fora
# enquanto o projeto não suporta bicos endurecidos.
STAINLESS_STEEL_HRC = 20

# Chaves que descrevem a própria relação de herança e não devem vazar para o preset achatado.
_LINK_KEYS = ("inherits", "include")
# Chaves de identidade que só valem para o preset que as declara.
_OWN_ONLY_KEYS = ("setting_id", "instantiation")


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class Printer:
    preset: str
    key: str
    model: str
    nozzle: float
    bed_x: float
    bed_y: float
    max_z: float


@dataclass(frozen=True)
class ProcessPreset:
    preset: str
    layer_height: float
    description: str


@dataclass(frozen=True)
class FilamentPreset:
    preset: str
    material: str
    filament_type: str
    vendor: str
    density: float
    nozzle_temperature: int
    nozzle_temperature_range: tuple[int, int]
    max_volumetric_speed: float


def first(value: Any) -> Any:
    """Presets guardam muitos valores como lista (um item por extrusor); usamos o primeiro."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


class PresetLibrary:
    def __init__(self, raw: dict[str, tuple[str, dict[str, Any]]]):
        # nome -> (tipo, conteúdo bruto do arquivo)
        self._raw = raw
        self._resolved: dict[str, dict[str, Any]] = {}

    @classmethod
    def load(cls, profiles_dir: Path) -> "PresetLibrary":
        if not profiles_dir.is_dir():
            raise CatalogError(
                f"Pasta de presets do Bambu Studio não encontrada: {profiles_dir}. "
                "Instale o Bambu Studio ou defina FILAMENTOR_PROFILES_DIR."
            )
        raw: dict[str, tuple[str, dict[str, Any]]] = {}
        for kind in PRESET_KINDS:
            for path in sorted((profiles_dir / kind).glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                # Arquivos auxiliares (mapas de IDs etc.) não têm "name".
                if isinstance(data, dict) and "name" in data:
                    raw[data["name"]] = (kind, data)
        return cls(raw)

    def kind(self, name: str) -> str:
        return self._entry(name)[0]

    def names(self, kind: str) -> list[str]:
        return [name for name, (k, _) in self._raw.items() if k == kind]

    def resolve(self, name: str) -> dict[str, Any]:
        """Retorna o preset com toda a cadeia de `inherits`/`include` aplicada."""
        return dict(self._resolve(name, ()))

    def _entry(self, name: str) -> tuple[str, dict[str, Any]]:
        try:
            return self._raw[name]
        except KeyError:
            raise CatalogError(f"Preset não encontrado: {name}") from None

    def _resolve(self, name: str, stack: tuple[str, ...]) -> dict[str, Any]:
        if name in self._resolved:
            return self._resolved[name]
        if name in stack:
            raise CatalogError(f"Herança circular: {' -> '.join((*stack, name))}")
        _, own = self._entry(name)
        stack = (*stack, name)

        merged: dict[str, Any] = {}
        if own.get("inherits"):
            merged.update(self._resolve(own["inherits"], stack))
        for template in own.get("include", []):
            merged.update(self._resolve(template, stack))
        for key in _OWN_ONLY_KEYS:
            merged.pop(key, None)
        merged.update(own)
        for key in _LINK_KEYS:
            merged.pop(key, None)
        self._resolved[name] = merged
        return merged


class Catalog:
    """Visão do catálogo restrita ao escopo do Filamentor (A1/A1 mini, PLA/PETG/TPU, bico inox)."""

    def __init__(self, library: PresetLibrary):
        self.library = library

    def _instantiable(self, kind: str) -> list[tuple[str, dict[str, Any]]]:
        result = []
        for name in self.library.names(kind):
            preset = self.library.resolve(name)
            if preset.get("instantiation") == "true":
                result.append((name, preset))
        return result

    def printers(self) -> list[Printer]:
        printers = []
        for name, preset in self._instantiable("machine"):
            key = SUPPORTED_PRINTER_MODELS.get(preset.get("printer_model", ""))
            if not key:
                continue
            xs, ys = zip(
                *(map(float, point.split("x")) for point in preset["printable_area"]), strict=True
            )
            printers.append(
                Printer(
                    preset=name,
                    key=key,
                    model=preset["printer_model"],
                    nozzle=float(first(preset["nozzle_diameter"])),
                    bed_x=max(xs) - min(xs),
                    bed_y=max(ys) - min(ys),
                    max_z=float(preset["printable_height"]),
                )
            )
        return sorted(printers, key=lambda p: (p.key, p.nozzle))

    def printer(self, machine_preset: str) -> Printer:
        for printer in self.printers():
            if printer.preset == machine_preset:
                return printer
        raise CatalogError(f"Impressora fora do escopo do Filamentor: {machine_preset}")

    def processes(self, machine_preset: str) -> list[ProcessPreset]:
        self.printer(machine_preset)
        processes = [
            ProcessPreset(
                preset=name,
                layer_height=float(preset["layer_height"]),
                description=preset.get("description", ""),
            )
            for name, preset in self._instantiable("process")
            if machine_preset in preset.get("compatible_printers", [])
        ]
        return sorted(processes, key=lambda p: (p.layer_height, p.preset))

    def filaments(self, machine_preset: str, material: str | None = None) -> list[FilamentPreset]:
        self.printer(machine_preset)
        filaments = []
        for name, preset in self._instantiable("filament"):
            if machine_preset not in preset.get("compatible_printers", []):
                continue
            filament_type = first(preset.get("filament_type"))
            family = MATERIAL_FAMILIES.get(filament_type)
            if not family or (material and family != material):
                continue
            if first(preset.get("filament_is_support")) == "1":
                continue
            if int(first(preset.get("required_nozzle_HRC")) or 0) > STAINLESS_STEEL_HRC:
                continue
            filaments.append(
                FilamentPreset(
                    preset=name,
                    material=family,
                    filament_type=filament_type,
                    vendor=first(preset.get("filament_vendor")) or "",
                    density=float(first(preset["filament_density"])),
                    nozzle_temperature=int(first(preset["nozzle_temperature"])),
                    nozzle_temperature_range=(
                        int(first(preset["nozzle_temperature_range_low"])),
                        int(first(preset["nozzle_temperature_range_high"])),
                    ),
                    max_volumetric_speed=float(first(preset["filament_max_volumetric_speed"])),
                )
            )
        return sorted(filaments, key=lambda f: (f.material, f.vendor != "Bambu Lab", f.preset))


@lru_cache
def get_catalog() -> Catalog:
    return Catalog(PresetLibrary.load(get_settings().profiles_dir))
