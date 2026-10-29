"""GGUF model identity verification.

Model filenames and UI labels are not proof of what a checkpoint contains. This
module reads GGUF metadata directly so startup can verify that the language model
and the multimodal projector are the architecture the application expects, instead
of trusting a hand-renamed file (a previous release shipped Qwen2-VL weights under
a ``qwen3-vl`` filename).
"""

from dataclasses import dataclass
from pathlib import Path
import struct

# Supported language-model architecture -> projector types it accepts.
#
# The bundled local model is Qwen3.5-2B: GGUF architecture ``qwen35`` paired with a
# ``qwen3vl_merger`` vision projector. Qwen2-VL (``qwen2vl`` + ``qwen2vl_merger``)
# stays in the mapping so an existing installation can be rolled back to the
# previous weights without editing code, while a cross-generation pairing (for
# example new Qwen3.5 weights with the old Qwen2-VL projector) is still rejected.
SUPPORTED_MODEL_PAIRS: dict[str, tuple[str, ...]] = {
    "qwen35": ("qwen3vl_merger",),
    "qwen2vl": ("qwen2vl_merger",),
}
EXPECTED_LM_ARCHITECTURES = set(SUPPORTED_MODEL_PAIRS)
EXPECTED_PROJECTOR_MARKERS = tuple(sorted({marker for markers in SUPPORTED_MODEL_PAIRS.values() for marker in markers}))

_GGUF_MAGIC = b"GGUF"
_NUMERIC_FORMATS: dict[int, tuple[str, int]] = {
    0: ("<B", 1),
    1: ("<b", 1),
    2: ("<H", 2),
    3: ("<h", 2),
    4: ("<I", 4),
    5: ("<i", 4),
    6: ("<f", 4),
    7: ("<?", 1),
    10: ("<Q", 8),
    11: ("<q", 8),
    12: ("<d", 8),
}


@dataclass(frozen=True)
class ModelIdentity:
    """Parsed GGUF identity facts."""

    path: Path
    architecture: str
    name: str
    metadata: dict[str, object]

    def is_valid_language_model(self) -> bool:
        """Return True if the architecture matches the supported VL family."""
        return self.architecture.lower() in EXPECTED_LM_ARCHITECTURES

    def is_valid_projector(self) -> bool:
        """Return True if the projector declares a compatible VL merger type."""
        projector_type = str(self.metadata.get("clip.projector_type", "")).lower()
        if projector_type:
            return any(marker in projector_type for marker in EXPECTED_PROJECTOR_MARKERS)
        arch = str(self.metadata.get("general.architecture", "")).lower()
        return any(marker in arch for marker in ("qwen2vl", "qwen3vl"))


def _read_string(fh) -> str:
    (length,) = struct.unpack("<Q", fh.read(8))
    if length > 16_000_000:
        raise ValueError("GGUF string length is implausibly large")
    return fh.read(length).decode("utf-8", errors="replace")


def _skip_value(fh, value_type: int) -> object:
    """Read a scalar value, or skip an array, returning scalars we care about."""
    if value_type == 8:  # string
        return _read_string(fh)
    if value_type == 9:  # array
        (element_type,) = struct.unpack("<I", fh.read(4))
        (count,) = struct.unpack("<Q", fh.read(8))
        if count > 1_000_000:
            raise ValueError("GGUF array count is implausibly large")
        for _ in range(count):
            _skip_value(fh, element_type)
        return None
    fmt_size = _NUMERIC_FORMATS.get(value_type)
    if fmt_size is None:
        raise ValueError(f"Unsupported GGUF value type: {value_type}")
    fmt, size = fmt_size
    raw = fh.read(size)
    if len(raw) != size:
        raise ValueError("Truncated GGUF value")
    return struct.unpack(fmt, raw)[0]


def read_gguf_metadata(path: str | Path) -> ModelIdentity:
    """Parse the GGUF key/value header.

    Args:
        path: Path to a ``.gguf`` file.

    Returns:
        ModelIdentity with architecture, name, and parsed metadata.

    Raises:
        ValueError: If the file is not a readable GGUF container.
        OSError: If the file cannot be opened.
    """
    p = Path(path)
    with open(p, "rb") as fh:
        magic = fh.read(4)
        if magic != _GGUF_MAGIC:
            raise ValueError(f"{p.name}: not a GGUF file (magic={magic!r})")
        (version,) = struct.unpack("<I", fh.read(4))
        if version < 2 or version > 3:
            raise ValueError(f"{p.name}: unsupported GGUF version {version}")
        struct.unpack("<Q", fh.read(8))  # tensor count
        (kv_count,) = struct.unpack("<Q", fh.read(8))
        if kv_count > 10_000_000:
            raise ValueError(f"{p.name}: implausible metadata count {kv_count}")

        metadata: dict[str, object] = {}
        for _ in range(kv_count):
            key = _read_string(fh)
            (value_type,) = struct.unpack("<I", fh.read(4))
            value = _skip_value(fh, value_type)
            if value is not None:
                metadata[key] = value

    architecture = str(metadata.get("general.architecture", "")).strip()
    name = str(metadata.get("general.name", "")).strip()
    return ModelIdentity(path=p, architecture=architecture, name=name, metadata=metadata)


def verify_local_model_pair(model_path: str | Path, mmproj_path: str | Path) -> list[str]:
    """Verify a local language model + projector pair.

    Args:
        model_path: GGUF language-model checkpoint.
        mmproj_path: GGUF multimodal projector.

    Returns:
        List of human-readable problems. Empty means the pair is consistent.
    """
    problems: list[str] = []
    try:
        lm = read_gguf_metadata(model_path)
    except (OSError, ValueError) as err:
        problems.append(f"Language model unreadable: {err}")
        lm = None
    if lm is not None and not lm.is_valid_language_model():
        problems.append(
            f"Language model architecture is {lm.architecture!r}; expected one of {sorted(EXPECTED_LM_ARCHITECTURES)}."
        )

    try:
        proj = read_gguf_metadata(mmproj_path)
    except (OSError, ValueError) as err:
        problems.append(f"Vision projector unreadable: {err}")
        proj = None
    if proj is not None:
        if not proj.is_valid_projector():
            problems.append(
                "Vision projector type is "
                f"{proj.metadata.get('clip.projector_type', proj.architecture)!r}; "
                "expected a Qwen3.5-VL/Qwen2-VL merger."
            )
        if lm is not None:
            expected_markers = SUPPORTED_MODEL_PAIRS.get(lm.architecture.lower())
            projector_type = str(proj.metadata.get("clip.projector_type", "") or proj.architecture).lower()
            if expected_markers is not None and not any(m in projector_type for m in expected_markers):
                problems.append(
                    f"Architecture mismatch: {lm.architecture!r} language model expects projector "
                    f"{list(expected_markers)}, got {projector_type!r}."
                )

    return problems
