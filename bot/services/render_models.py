from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable


class OutputFormat(StrEnum):
    GIF = "gif"
    VIDEO = "video"
    FILE = "file"


class WatermarkPosition(StrEnum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


class SourceKind(StrEnum):
    CUSTOM_EMOJI = "custom_emoji"
    STICKER = "sticker"
    USER_MEDIA = "user_media"


@dataclass(slots=True)
class RenderSettings:
    background_color: str = "#000000"
    width: int = 1920
    height: int = 530
    fps: int = 60
    output_format: OutputFormat = OutputFormat.GIF
    emoji_color: str | None = None
    emoji_size: int = 55
    watermark_text: str | None = None
    watermark_font: str = "Roboto"
    watermark_color: str = "#FFFFFF"
    watermark_position: WatermarkPosition = WatermarkPosition.BOTTOM_RIGHT
    watermark_size: int = 5
    custom_background_file_id: str | None = None
    custom_background_suffix: str | None = None
    custom_background_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RenderSettings":
        defaults = cls()
        try:
            return cls(
                background_color=str(raw.get("background_color", defaults.background_color)),
                width=int(raw.get("width", defaults.width)),
                height=int(raw.get("height", defaults.height)),
                fps=60,
                output_format=OutputFormat(raw.get("output_format", defaults.output_format)),
                emoji_color=(str(raw["emoji_color"]) if raw.get("emoji_color") else None),
                emoji_size=int(raw.get("emoji_size", defaults.emoji_size)),
                watermark_text=(str(raw["watermark_text"]) if raw.get("watermark_text") else None),
                watermark_font=str(raw.get("watermark_font", defaults.watermark_font)),
                watermark_color=str(raw.get("watermark_color", defaults.watermark_color)),
                watermark_position=WatermarkPosition(
                    raw.get("watermark_position", defaults.watermark_position)
                ),
                watermark_size=max(
                    1,
                    min(20, int(raw.get("watermark_size", defaults.watermark_size))),
                ),
                custom_background_file_id=(
                    str(raw["custom_background_file_id"])
                    if raw.get("custom_background_file_id")
                    else None
                ),
                custom_background_suffix=(
                    str(raw["custom_background_suffix"])
                    if raw.get("custom_background_suffix")
                    else None
                ),
                custom_background_label=(
                    str(raw["custom_background_label"])
                    if raw.get("custom_background_label")
                    else None
                ),
            )
        except (TypeError, ValueError):
            return defaults


@dataclass(slots=True)
class RenderSource:
    kind: SourceKind
    file_id: str
    suffix: str
    label: str = "Медиа"
    recolorable: bool = False
    local_path: Path | None = None

    def to_session_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "file_id": self.file_id,
            "suffix": self.suffix,
            "label": self.label,
            "recolorable": self.recolorable,
        }

    @classmethod
    def from_session_dict(cls, raw: dict[str, Any]) -> "RenderSource":
        return cls(
            kind=SourceKind(raw["kind"]),
            file_id=str(raw["file_id"]),
            suffix=str(raw["suffix"]),
            label=str(raw.get("label", "Медиа")),
            recolorable=bool(raw.get("recolorable", False)),
        )


ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class RenderRequest:
    sources: list[RenderSource]
    settings: RenderSettings
    background_source: RenderSource | None = None
    preview: bool = False
    progress: ProgressCallback | None = None


@dataclass(slots=True)
class RenderResult:
    path: Path
    output_format: OutputFormat
    width: int
    height: int
    duration: float
    fps: int
    temporary_paths: list[Path] = field(default_factory=list)
