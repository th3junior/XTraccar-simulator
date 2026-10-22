from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ViolationDef:
    id: str
    label: str
    alarm: str
    description: str
    speed_delta_kmh: float = 0.0
    force_ignition: bool | None = None
    power_spike: float | None = None


VIOLATIONS: dict[str, ViolationDef] = {
    "overspeed": ViolationDef(
        "overspeed",
        "Excesso de velocidade",
        "overspeed",
        "Pico de velocidade acima do limite",
        speed_delta_kmh=45,
    ),
    "hardAcceleration": ViolationDef(
        "hardAcceleration",
        "Aceleração brusca",
        "hardAcceleration",
        "Aceleração forte detectada",
        speed_delta_kmh=25,
    ),
    "hardBraking": ViolationDef(
        "hardBraking",
        "Frenagem brusca",
        "hardBraking",
        "Redução brusca de velocidade",
        speed_delta_kmh=-35,
    ),
    "hardCornering": ViolationDef(
        "hardCornering",
        "Curva brusca",
        "hardCornering",
        "Manobra lateral agressiva",
    ),
    "sos": ViolationDef("sos", "SOS / pânico", "sos", "Botão de emergência"),
    "vibration": ViolationDef(
        "vibration",
        "Vibração",
        "vibration",
        "Alarme de vibração (anti-furto)",
    ),
    "tampering": ViolationDef(
        "tampering",
        "Violação do equipamento",
        "tampering",
        "Possível adulteração do rastreador",
    ),
    "powerCut": ViolationDef(
        "powerCut",
        "Corte de energia (12V)",
        "powerCut",
        "Alimentação externa removida — power = 0",
        force_ignition=False,
    ),
    "powerRestored": ViolationDef(
        "powerRestored",
        "Energia restaurada (12V)",
        "powerRestored",
        "Alimentação externa reconectada — rastreador volta a carregar",
    ),
    "jamming": ViolationDef(
        "jamming",
        "Jammer / interferência",
        "jamming",
        "Interferência de sinal GPS/GSM",
    ),
    "lowBattery": ViolationDef(
        "lowBattery",
        "Bateria baixa",
        "lowBattery",
        "Bateria interna do rastreador crítica",
    ),
    "geofenceEnter": ViolationDef(
        "geofenceEnter",
        "Entrada em cerca",
        "geofenceEnter",
        "Entrada em área monitorada",
    ),
    "geofenceExit": ViolationDef(
        "geofenceExit",
        "Saída de cerca",
        "geofenceExit",
        "Saída de área monitorada",
    ),
}


def list_violations() -> list[dict[str, Any]]:
    return [
        {
            "id": v.id,
            "label": v.label,
            "alarm": v.alarm,
            "description": v.description,
        }
        for v in VIOLATIONS.values()
    ]
