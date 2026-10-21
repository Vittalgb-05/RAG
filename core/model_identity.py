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

# Expected identities for the bundled local model.
EXPECTED_LM_ARCHITECTURES = {"qwen2vl", "qwen3vl"}
EXPECTED_PROJECTOR_MARKERS = ("qwen2vl_merger", "qwen3vl_merger")

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
                "expected a Qwen2-VL/Qwen3-VL merger."
            )
        if lm is not None and "qwen2" in lm.architecture.lower() and "qwen3" in proj.architecture.lower():
            problems.append("Architecture mismatch: Qwen2 language model paired with a Qwen3 projector.")
        if lm is not None and "qwen3" in lm.architecture.lower() and "qwen2" in proj.architecture.lower():
            problems.append("Architecture mismatch: Qwen3 language model paired with a Qwen2 projector.")

    return problems
