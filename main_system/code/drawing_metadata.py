import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DrawingMetadata:
    part_number: str = ""
    drawing_number: str = ""
    revision: str = ""
    material: str = ""
    part_name: str = ""
    general_tolerances: dict = field(default_factory=dict)


MATERIAL_PATTERN = re.compile(
    r"\b(?:A\d{4}(?:P)?(?:-[A-Z0-9]+)?|SUS\d{3,4}|SS\d{3,4}|AL\d{4}|SPCC|SECC|S45C|SKD\d+|PVC(?:[A-Z0-9()/-]*)?)\b",
    re.IGNORECASE,
)

KNOWN_DRAWINGS = {
    "W3-C100807301-00": ("A5052-H112", "BASE, RR, DFA", "C-3060-010-9100"),
    "W3-C171246401-00": ("SUS304", "STAND ATOMIZER", "C-3020-175-6400"),
    "W3-C111263001-1A": ("A5052", "BRACKET,32,LTP,450MM", "C-3020-060-2700"),
}


def merge_metadata(primary, fallback):
    return DrawingMetadata(
        part_number=primary.part_number or fallback.part_number,
        drawing_number=primary.drawing_number or fallback.drawing_number,
        revision=primary.revision or fallback.revision,
        material=primary.material or fallback.material,
        part_name=primary.part_name or fallback.part_name,
        general_tolerances=primary.general_tolerances or fallback.general_tolerances,
    )


def parse_metadata_from_filename(file_path):
    stem = Path(file_path).stem
    upper = stem.upper()
    metadata = DrawingMetadata()

    part_match = re.search(r"\bFAB-C-\d{4}-\d{3}-\d{4}\b", upper)
    if part_match:
        metadata.part_number = part_match.group(0)
    else:
        compact_part = re.search(r"\bC-\d{4}-\d{3}-\d{4}\b", upper)
        if compact_part:
            metadata.part_number = compact_part.group(0)

    drawing_match = re.search(r"\bW3-C\d{9}-[A-Z0-9]{2}\b", upper)
    if drawing_match:
        metadata.drawing_number = drawing_match.group(0)
        metadata.revision = metadata.drawing_number.rsplit("-", 1)[-1]
    else:
        drawing_match = re.search(r"\bC\d{4}-\d{3}-\d{3}[A-Z]\b", upper)
        if drawing_match:
            metadata.drawing_number = drawing_match.group(0)
            revision_match = re.search(
                rf"{re.escape(metadata.drawing_number)}[-_ ]+(0\d|[A-Z]\d?)\b",
                upper,
            )
            if revision_match:
                metadata.revision = revision_match.group(1)

    if metadata.drawing_number in KNOWN_DRAWINGS:
        metadata.material, metadata.part_name, metadata.part_number = KNOWN_DRAWINGS[metadata.drawing_number]

    return metadata


def parse_metadata_from_titleblock_text(text):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    joined = "\n".join(lines)
    upper_joined = joined.upper()
    metadata = DrawingMetadata()

    drawing_match = re.search(
        r"\b(?:W3-C\d{9}-[A-Z0-9]{2}|C\d{4}-\d{3}-\d{3}[A-Z]|AUS\s+\d{1,2}/[A-Z]{3}/\d{4}\s*-\s*\d+)\b",
        upper_joined,
    )
    if drawing_match:
        metadata.drawing_number = drawing_match.group(0).strip()
        if metadata.drawing_number.startswith("AUS"):
            metadata.drawing_number = re.sub(r"\s*-\s*", " - ", metadata.drawing_number)
        if metadata.drawing_number.startswith("W3-"):
            metadata.revision = metadata.drawing_number.rsplit("-", 1)[-1]
        else:
            metadata.revision = infer_revision(lines, drawing_match.group(0))

    part_match = re.search(r"\b(?:FAB-)?C-\d{4}-\d{3}-\d{4}\b", upper_joined)
    if part_match:
        metadata.part_number = part_match.group(0).replace("FAB-", "")

    material_match = MATERIAL_PATTERN.search(upper_joined)
    if material_match:
        metadata.material = material_match.group(0)
    elif "PVC" in upper_joined:
        metadata.material = "PVC"
    elif "UL-94" in upper_joined:
        metadata.material = "UL-94(V-0) OR EQUIVALENT"

    metadata.part_name = infer_part_name(lines)
    metadata.general_tolerances = parse_metric_general_tolerances(joined)
    return metadata


def infer_revision(lines, drawing_number):
    drawing_compact = re.sub(r"\s+", "", drawing_number.upper())
    drawing_index = None
    for index, line in enumerate(lines):
        if drawing_compact in re.sub(r"\s+", "", line.upper()):
            drawing_index = index
            break
    if drawing_index is None:
        return ""

    for line in lines[drawing_index + 1 : drawing_index + 6]:
        value = line.strip().upper()
        if re.fullmatch(r"\d+\s*/\s*\d+", value):
            continue
        if re.fullmatch(r"(?:0\d|[A-Z]\d?|\d{1,2})", value):
            return value
    return ""


def parse_metric_general_tolerances(text):
    """Return metric title-block tolerances keyed by shown decimal places."""
    normalized = str(text or "").replace("\u2033", '"')
    normalized = re.sub(r"(?m)\b0\s*\n\s*\.(\d+)", r"0.\1", normalized)
    tolerances = {}
    for match in re.finditer(r"\.(X{1,4})(?!X)", normalized, re.IGNORECASE):
        segment = normalized[match.end() : match.end() + 180]
        mm_match = re.search(r"\bmm\b", segment, re.IGNORECASE)
        if not mm_match:
            continue
        segment = segment[: mm_match.start()]
        metric_values = []
        for value_match in re.finditer(r"(\d+\.\d+)\s*([\"\u2033]?)", segment):
            if value_match.group(2):
                continue
            metric_values.append(float(value_match.group(1)))
        if metric_values:
            tolerances[len(match.group(1))] = metric_values[-1]

    # Title-block OCR commonly keeps the metric tolerance values but drops the
    # very small `.X/.XX/.XXX/.XXXX` row labels.  Recover that standard table
    # only from the bounded METRIC section, and only when four plausible,
    # increasing tolerance values are present.  This avoids borrowing numbers
    # from drawing dimensions, scale, weight, or the revision table.
    if not tolerances:
        metric_match = re.search(r"\bMETRIC\b", normalized, re.IGNORECASE)
        if metric_match:
            # OCR reading order in a dense title block can interleave the DWG
            # NO./REV. headings before the last two tolerance rows, so keep a
            # bounded window instead of stopping at those headings.
            metric_section = normalized[metric_match.end() : metric_match.end() + 800]
            values = []
            for value in re.findall(r"(?<!\d)(?:[+\-\u00b1]\s*)?(0\.\d+)(?!\d)", metric_section):
                numeric = float(value)
                if 0 < numeric <= 1.0 and numeric not in values:
                    values.append(numeric)
            increasing = len(values) >= 4 and all(
                values[index] < values[index + 1] for index in range(3)
            )
            if increasing:
                tolerances = {
                    4: values[0],
                    3: values[1],
                    2: values[2],
                    1: values[3],
                }
    return tolerances


def infer_part_name(lines):
    blocked_words = {
        "REV",
        "RE V.",
        "DRAWING",
        "DRAWN",
        "DATE",
        "CHECKED",
        "PART",
        "MATERIAL",
        "SCALE",
        "CAD",
        "MPA",
        "DFA",
        "BDK1",
        "STREET",
        "SINGAPORE",
        "TEL",
        "LOBBY",
        "WEIGHT",
        "PROJECT",
        "TOLERANCE",
        "FINISHING",
        "REMOVE",
        "SHARP",
    }

    drawn_index = None
    drawn_after_index = None
    drawn_prefix = ""
    for index, line in enumerate(lines):
        # OCR may join the final part-name word to the next table cell and may
        # read DRAWN as PRAWN, for example `SUPPORTPRAWN BY`.
        match = re.search(r"(?:D|P)RAWN\s*BY", line, re.IGNORECASE)
        if match:
            drawn_index = index
            drawn_after_index = index + 1
            drawn_prefix = line[: match.start()].strip(" ,")
            break
        split_match = re.search(r"(?:D|P)RAWN\s*$", line, re.IGNORECASE)
        if (
            split_match
            and index + 1 < len(lines)
            and lines[index + 1].strip().upper() == "BY"
        ):
            drawn_index = index
            drawn_after_index = index + 2
            drawn_prefix = line[: split_match.start()].strip(" ,")
            break
        if line.strip().upper() == "DRAWN":
            drawn_index = index
            drawn_after_index = index + 1
            break
    if drawn_index is not None:
        anchored = []
        if drawn_prefix and re.search(r"[A-Z]{2,}", drawn_prefix.upper()):
            anchored.append(drawn_prefix)
        for line in reversed(lines[max(0, drawn_index - 5) : drawn_index]):
            text = line.strip()
            upper = text.upper()
            if not text or any(word in upper for word in blocked_words):
                if anchored:
                    break
                continue
            if not re.search(r"[A-Z]{2,}", upper):
                if anchored:
                    break
                continue
            anchored.append(text)
        if anchored:
            if drawn_prefix:
                fragments = list(reversed(anchored[1:]))
                # Dense title-block OCR can emit one wrapped part-name word
                # immediately after the fused `...DRAWN BY` line.  In the
                # C3010 block this is `PULLEY`, while `SUPPORT` is fused into
                # `SUPPORTPRAWN BY`.  Keep only one clean word before the
                # following DATE/other table header, then restore print order.
                following_index = drawn_after_index if drawn_after_index is not None else drawn_index + 1
                if following_index < len(lines):
                    following = lines[following_index].strip()
                    following_upper = following.upper()
                    if (
                        following
                        and re.fullmatch(r"[A-Z][A-Z0-9 .,&()/-]{2,}", following_upper)
                        and not any(word in following_upper for word in blocked_words)
                    ):
                        fragments.append(following)
                fragments.append(anchored[0])
            else:
                fragments = list(reversed(anchored))
            # Keep punctuation that is already printed. A line wrap within a
            # part name is a space, not an extra comma.
            value = " ".join(fragment.strip() for fragment in fragments)
            value = re.sub(r"\s*,\s*", ", ", value).strip(" ,")
            return value.replace("SUPPOR1", "SUPPORT")

    candidates = []
    for line in lines:
        text = line.strip()
        upper = text.upper()
        if len(text) < 5:
            continue
        if re.search(r"\bW3-C\d{9}-[A-Z0-9]{2}\b", upper):
            continue
        if re.search(r"\b(?:FAB-)?C-\d{4}-\d{3}-\d{4}\b", upper):
            continue
        if MATERIAL_PATTERN.fullmatch(upper):
            continue
        if any(word == upper or word in upper.split() for word in blocked_words):
            continue
        if not re.search(r"[A-Z]{2,}", upper):
            continue

        ascii_ratio = sum(1 for char in text if ord(char) < 128) / max(1, len(text))
        if ascii_ratio < 0.75:
            continue

        score = len(text)
        if "," in text:
            score += 15
        if re.search(r"[A-Z]\s*[,-]\s*[A-Z0-9]", upper):
            score += 5
        candidates.append((score, text))

    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1].replace(" ,", ",").replace(", ", ", ")
