"""
VMF Renamer – Core logic module.
Reads MediaInfo from video files and builds standardized torrent tracker filenames.

Output format example:
  Spider-Man.No.Way.Home.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR.mkv
"""

import os
import re
import json
import unicodedata
from typing import Any, Optional

from pymediainfo import MediaInfo
import guessit as guessit_module


# ─── Audio codec mapping ────────────────────────────────────────────────────────

AUDIO_FORMAT_MAP: dict[str, str] = {
    "DTS": "DTS",
    "AAC": "AAC",
    "AAC LC": "AAC",
    "AC-3": "DD",
    "E-AC-3": "DDP",
    "A_EAC3": "DDP",
    "Enhanced AC-3": "DDP",
    "MLP FBA": "TrueHD",
    "FLAC": "FLAC",
    "Opus": "Opus",
    "Vorbis": "VORBIS",
    "PCM": "LPCM",
    "MPEG Audio": "MP3",
}

AUDIO_ADDITIONAL_MAP: dict[str, str] = {
    "XLL": "-HD.MA",
    "XLL X": ":X",
    "ES": "-ES",
}

AUDIO_ATMOS_INDICATORS: list[str] = [
    "JOC", "Atmos", "16-ch", "Atmos Audio",
    "TrueHD Atmos", "E-AC-3 JOC", "Dolby Atmos",
]

AUDIO_COMMERCIAL_MAP: dict[str, str] = {
    # Order matters: longer/more-specific keys must come first
    "Dolby Digital Plus": "DDP",
    "Dolby TrueHD": "TrueHD",
    "DTS:X Master Audio": "DTS:X",
    "DTS-HD Master Audio": "DTS-HD.MA",
    "DTS-HD High": "DTS-HD.HRA",
    "DTS-ES": "DTS-ES",
    "Free Lossless Audio Codec": "FLAC",
    "Dolby Digital": "DD",
}

AUDIO_CODEC_RANK: dict[str, int] = {
    "TrueHD": 100,
    "DTS:X": 95,
    "DTS-HD.MA": 90,
    "DDP": 60,
    "FLAC": 85,
    "LPCM": 80,
    "PCM": 80,
    "DTS-HD.HRA": 70,

    "DTS": 50,
    "DD": 40,
    "AAC": 30,
    "VORBIS": 20,
    "MP3": 10,
}


# ─── Helper: channel count ───────────────────────────────────────────────────────

def _count_channels(channels_raw: Any, channel_layout: str, additional: str, format_name: str) -> str:
    """Determine channel count string like '5.1', '7.1', '7.1.4' (Atmos)."""
    s = str(channels_raw).strip() if channels_raw else ""
    m = re.search(r"\d+", s)
    if not m:
        return ""
    channels = int(m.group(0))
    layout = (channel_layout or "").upper()

    # Detect height channels (Atmos / immersive)
    height_indicators = [
        "TFC", "TFL", "TFR", "TBL", "TBR", "TBC",
        "TSL", "TSR", "TLS", "TRS",
        "VHC", "VHL", "VHR",
    ]
    has_height = any(ind in layout for ind in height_indicators)
    is_atmos = any(ind in str(additional) for ind in AUDIO_ATMOS_INDICATORS)

    if has_height or is_atmos:
        # Parse bed, LFE, height
        parts = layout.split()
        bed = lfe = height = 0
        lfe_ids = {"LFE"}
        bed_ids = {
            "L", "R", "C", "FC", "LS", "RS", "SL", "SR",
            "BL", "BR", "BC", "SB", "LB", "RB", "CB", "CS",
            "FLC", "FRC", "LC", "RC", "LW", "RW",
        }
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if "LFE" in p:
                lfe += 1
            elif any(h in p for h in height_indicators):
                height += 1
            elif p in bed_ids:
                bed += 1
        if height > 0:
            return f"{bed}.{lfe}.{height}" if lfe else f"{bed}.0.{height}"

    # Standard layout
    lfe_count = layout.count("LFE")
    if lfe_count >= 1:
        return f"{channels - lfe_count}.{lfe_count}"

    # Fallback
    if channels <= 2:
        return f"{channels}.0"
    elif channels == 6:
        return "5.1"
    elif channels == 8:
        return "7.1"
    else:
        return f"{channels - 1}.1"


# ─── MediaInfo extraction ────────────────────────────────────────────────────────

def extract_mediainfo(filepath: str) -> dict[str, Any]:
    """Extract MediaInfo as a Python dict from a video file."""
    mi = MediaInfo.parse(filepath, output="JSON")
    return json.loads(mi)


def _get_track(mi_data: dict[str, Any], track_type: str, index: int = 0) -> dict[str, Any]:
    """Get a specific track from MediaInfo data."""
    tracks = mi_data.get("media", {}).get("track", [])
    typed = [t for t in tracks if t.get("@type") == track_type]
    if index < len(typed):
        return typed[index]
    return {}


def _get_best_audio_track(mi_data: dict[str, Any]) -> dict[str, Any]:
    """Find the audio track with the highest quality codec."""
    tracks = mi_data.get("media", {}).get("track", [])
    audio_tracks = [t for t in tracks if t.get("@type") == "Audio"]
    if not audio_tracks:
        return {}

    best_track = audio_tracks[0]
    best_score = -1

    for track in audio_tracks:
        info = detect_audio(track)
        codec = info.get("audio_codec", "")
        score = AUDIO_CODEC_RANK.get(codec, 0)
        # Bonus for Atmos
        if info.get("audio_atmos"):
            score += 5
        # Bonus for more channels
        try:
            chan_str = info.get("audio_channels", "2.0")
            chan_parts = chan_str.split('.')
            chan_val = float(chan_parts[0]) + float(chan_parts[1]) * 0.1
            if len(chan_parts) > 2:
                chan_val += float(chan_parts[2]) * 0.01
            score += chan_val
        except:
            pass

        if score > best_score:
            best_score = score
            best_track = track

    return best_track


# ─── Detection functions ─────────────────────────────────────────────────────────

def detect_resolution(video_track: dict[str, Any]) -> str:
    """Detect resolution string: 2160p, 1080p, 720p, 480p, etc."""
    try:
        width = int(float(video_track.get("Width", 0)))
        height = int(float(video_track.get("Height", 0)))
    except (ValueError, TypeError):
        return ""

    scan = video_track.get("ScanType", "Progressive")
    suffix = "i" if scan and "Interlaced" in str(scan) else "p"

    # Map to standard resolutions
    if height >= 2000 or width >= 3800:
        return f"2160{suffix}"
    elif height >= 900 or width >= 1900:
        return f"1080{suffix}"
    elif height >= 600 or width >= 1200:
        return f"720{suffix}"
    elif height >= 500:
        return f"576{suffix}"
    elif height > 0:
        return f"480{suffix}"
    return ""


def detect_hdr(video_track: dict[str, Any]) -> str:
    """Detect HDR format: DV, HDR10+, HDR, PQ10, HLG, WCG."""
    hdr = ""
    dv = ""

    # Dolby Vision
    hdr_format = video_track.get("HDR_Format", "") or ""
    hdr_format_string = video_track.get("HDR_Format_String", "") or ""
    hdr_compat = video_track.get("HDR_Format_Compatibility", "") or ""

    if "Dolby Vision" in hdr_format or "Dolby Vision" in hdr_format_string:
        dv = "DV"

    # HDR10+ / HDR10
    all_hdr = f"{hdr_format} {hdr_format_string} {hdr_compat}"
    if "HDR10+" in all_hdr or "SMPTE ST 2094 App 4" in all_hdr:
        hdr = "HDR10+"
    elif "HDR10" in all_hdr:
        hdr = "HDR"
    elif "HDR" in all_hdr:
        hdr = "HDR"

    # HLG
    transfer = video_track.get("transfer_characteristics", "") or ""
    transfer_orig = video_track.get("transfer_characteristics_Original", "") or ""
    if "HLG" in transfer or "HLG" in transfer_orig:
        if hdr:
            hdr = f"{hdr}.HLG"
        else:
            hdr = "HLG"

    # PQ10 fallback
    if not hdr and ("PQ" in transfer or "PQ" in transfer_orig):
        colour = video_track.get("colour_primaries", "") or ""
        if "BT.2020" in colour or "REC.2020" in colour:
            hdr = "PQ10"

    # WCG fallback
    if not hdr and "BT.2020 (10-bit)" in transfer_orig:
        hdr = "WCG"

    result = f"{dv} {hdr}".strip() if dv or hdr else ""
    # Use dots for multi-part HDR
    return result.replace(" ", ".")


def detect_audio(audio_track: dict[str, Any]) -> dict[str, str]:
    """
    Detect audio codec and channels.
    Returns dict with keys: codec, channels, atmos (bool-ish string).
    """
    format_name = audio_track.get("Format", "") or ""
    commercial = audio_track.get("Format_Commercial", "") or audio_track.get("Format_Commercial_IfAny", "") or ""
    additional = audio_track.get("Format_AdditionalFeatures", "") or ""
    format_profile = audio_track.get("Format_Profile", "") or ""
    channels_raw = audio_track.get("Channels_Original", audio_track.get("Channels", ""))
    channel_layout = audio_track.get("ChannelLayout", "") or audio_track.get("ChannelLayout_Original", "") or ""

    # Determine codec
    codec = ""
    atmos = ""

    # Try commercial name first
    for key, value in AUDIO_COMMERCIAL_MAP.items():
        if key in commercial:
            codec = value
            break

    # Fallback to format
    if not codec:
        codec = AUDIO_FORMAT_MAP.get(format_name, format_name)
        extra = AUDIO_ADDITIONAL_MAP.get(additional, "")
        if extra:
            codec = f"{codec}{extra}"

    # Atmos detection
    if any(ind in str(additional) for ind in AUDIO_ATMOS_INDICATORS) or "Atmos" in commercial:
        atmos = "Atmos"

    # DTS:X detection
    if format_name.startswith("DTS") and additional and additional.endswith("X"):
        codec = "DTS:X"

    # MPEG Audio profile
    if format_name == "MPEG Audio":
        if "Layer 2" in format_profile:
            codec = "MP2"
        elif "Layer 3" in format_profile:
            codec = "MP3"

    # Channel count
    chan = _count_channels(channels_raw, channel_layout, additional, format_name)

    # Fix: DD can't be 7.1
    if codec == "DD" and chan == "7.1":
        codec = "DDP"

    return {
        "audio_codec": codec,
        "audio_channels": chan,
        "audio_atmos": atmos,
    }


def detect_video_encode(video_track: dict[str, Any], media_type: str) -> tuple[str, str]:
    """
    Detect video encode string and video codec.
    """
    format_name = video_track.get("Format", "") or ""
    format_profile = video_track.get("Format_Profile", "") or ""
    has_encode_settings = bool(video_track.get("Encoded_Library_Settings"))
    encoded_lib = video_track.get("Encoded_Library_Name", "") or ""

    video_codec = format_name
    video_encode = ""

    if format_name in ("AV1", "VP9", "VC-1"):
        video_encode = format_name
    elif media_type in ("ENCODE", "WEBRIP", "DVDRIP"):
        if format_name == "AVC":
            video_encode = "x264"
        elif format_name == "HEVC":
            video_encode = "x265"
        elif format_name == "MPEG-4 Visual" and encoded_lib:
            if "xvid" in encoded_lib.lower():
                video_encode = "XviD"
            elif "divx" in encoded_lib.lower():
                video_encode = "DivX"
    elif media_type in ("WEBDL", "HDTV"):
        if format_name == "AVC":
            video_encode = "H.264"
        elif format_name == "HEVC":
            video_encode = "H.265"
        if media_type == "HDTV" and has_encode_settings:
            video_encode = video_encode.replace("H.", "x")
    elif media_type in ("REMUX", "DISC"):
        # For REMUX/DISC, use codec name directly
        codec_map = {
            "AVC": "AVC",
            "HEVC": "HEVC",
            "VC-1": "VC-1",
            "MPEG Video": "MPEG-2",
        }
        video_encode = codec_map.get(format_name, format_name)
        if format_name == "MPEG Video":
            ver = video_track.get("Format_Version", "")
            if ver:
                video_encode = f"MPEG-{ver}"

    # Hi10P profile
    if format_profile == "High 10":
        video_encode = f"Hi10P.{video_encode}" if video_encode else "Hi10P"

    return video_encode, video_codec


def detect_source_type(filename: str) -> tuple[str, str]:
    """Detect source and type from filename."""
    fn = filename.lower()

    if "remux" in fn:
        media_type = "REMUX"
    elif any(w in fn for w in ["web-dl", "webdl", "web.dl"]):
        media_type = "WEBDL"
    elif "webrip" in fn or "web-rip" in fn:
        media_type = "WEBRIP"
    elif "hdtv" in fn:
        media_type = "HDTV"
    elif "dvdrip" in fn:
        media_type = "DVDRIP"
    elif "bdmv" in fn or "disc" in fn:
        media_type = "DISC"
    else:
        media_type = "ENCODE"

    if any(w in fn for w in ["bluray", "blu-ray", "blu.ray"]):
        source = "BluRay"
    elif "hddvd" in fn or "hd-dvd" in fn:
        source = "HDDVD"
    elif any(w in fn for w in ["web-dl", "webdl", "web.dl", "webrip", "web-rip", "web"]):
        source = "WEB"
    elif "hdtv" in fn:
        source = "HDTV"
    elif "dvdrip" in fn or "dvd" in fn:
        source = "DVD"
    elif media_type == "REMUX":
        source = "BluRay"
    else:
        source = ""

    return source, media_type


def detect_uhd(media_type: str, resolution: str, source: str) -> str:
    if resolution == "2160p" and media_type in ("DISC", "REMUX", "ENCODE"):
        return "UHD"
    if source in ("BluRay",) and "2160" in resolution:
        return "UHD"
    return ""


def detect_hybrid(filename: str) -> str:
    if "hybrid" in filename.lower():
        return "HYBRID"
    return ""


def detect_repack(filename: str) -> str:
    fn = filename.lower()
    if "repack" in fn:
        return "REPACK"
    elif "proper" in fn:
        return "PROPER"
    return ""


def detect_edition(filename: str) -> str:
    fn = filename.lower()
    editions = []
    edition_map = {
        "director's cut": "Directors.Cut",
        "directors cut": "Directors.Cut",
        "extended": "Extended",
        "extended edition": "Extended.Edition",
        "extended cut": "Extended.Cut",
        "unrated": "Unrated",
        "uncut": "Uncut",
        "theatrical": "Theatrical",
        "imax": "IMAX",
        "remastered": "Remastered",
        "criterion": "Criterion",
        "special edition": "Special.Edition",
        "dubbed": "DUB",
        " dubbed": "DUB",
        ".dub.": "DUB",
        ".dubbed.": "DUB"
    }
    for key, value in edition_map.items():
        if key in fn:
            editions.append(value)
            break
    
    # Special handle for .DUB. in middle of name
    if "DUB" not in editions and re.search(r'\.DUB\.', filename, re.I):
        editions.append("DUB")
        
    return ".".join(editions)


def detect_service(filename: str) -> str:
    """Detect streaming service from filename.
    Mapping aligned with Upload-Assistant / scene naming conventions.
    """
    fn = filename.upper()
    services = {
        # --- Major platforms ---
        "AMZN": "AMZN", "AMAZON": "AMZN",
        "NF": "NF", "NETFLIX": "NF",
        "DSNP": "DSNP",
        "ATVP": "ATVP",
        "HMAX": "HMAX",
        "MAX": "MAX",
        "HULU": "HULU",
        "PCOK": "PCOK",
        "PMTP": "PMTP", "PMNP": "PMNP", "PMNT": "PMNT",
        "HBO": "HBO",
        "MA": "MA",
        "IT": "iT",
        # --- Full list (Upload-Assistant aligned) ---
        "9NOW": "9NOW",
        "ADN": "ADN",
        "AE": "AE",
        "AJAZ": "AJAZ",
        "ALL4": "ALL4",
        "AMBC": "AMBC",
        "AMC": "AMC",
        "ANLB": "ANLB",
        "ANPL": "ANPL",
        "AOL": "AOL",
        "ARD": "ARD",
        "AS": "AS",
        "ATK": "ATK",
        "ATV": "ATV",
        "AUBC": "AUBC",
        "BCORE": "BCORE",
        "BETP": "BETP",
        "BILI": "BILI",
        "BKPL": "BKPL",
        "BLU": "BLU",
        "BNGE": "BNGE",
        "BOOM": "BOOM",
        "BP": "BP",
        "BRAV": "BRAV",
        "CBC": "CBC",
        "CBS": "CBS",
        "CC": "CC",
        "CCGC": "CCGC",
        "CHGD": "CHGD",
        "CMAX": "CMAX",
        "CMOR": "CMOR",
        "CMT": "CMT",
        "CN": "CN",
        "CNBC": "CNBC",
        "CNGO": "CNGO",
        "CNLP": "CNLP",
        "COOK": "COOK",
        "CORE": "CORE",
        "CR": "CR",
        "CRAV": "CRAV",
        "CRIT": "CRIT",
        "CRKI": "CRKI",
        "CRKL": "CRKL",
        "CSPN": "CSPN",
        "CTHP": "CTHP",
        "CTV": "CTV",
        "CUR": "CUR",
        "CW": "CW",
        "CWS": "CWS",
        "DARKROOM": "DARKROOM",
        "DAZN": "DAZN",
        "DCU": "DCU",
        "DDY": "DDY",
        "DEST": "DEST",
        "DF": "DF",
        "DHF": "DHF",
        "DISC": "DISC",
        "DIY": "DIY",
        "DOCC": "DOCC",
        "DOCPLAY": "DOCPLAY",
        "DPLY": "DPLY",
        "DRPO": "DRPO",
        "DSCP": "DSCP",
        "DSKI": "DSKI",
        "DSNY": "DSNY",
        "DTV": "DTV",
        "EPIX": "EPIX",
        "ESPN": "ESPN",
        "ESQ": "ESQ",
        "ETTV": "ETTV",
        "ETV": "ETV",
        "FAM": "FAM",
        "FANDOR": "FANDOR",
        "FJR": "FJR",
        "FMIO": "FMIO",
        "FOOD": "FOOD",
        "FOX": "FOX", "FOXN": "FOXN", "FOXP": "FOXP",
        "FP": "FP",
        "FPT": "FPT",
        "FREE": "FREE",
        "FTV": "FTV",
        "FUNI": "FUNI",
        "FXTL": "FXTL",
        "FYI": "FYI",
        "GC": "GC",
        "GLBL": "GLBL",
        "GLBO": "GLBO",
        "GLOB": "GLOB",
        "GO90": "GO90",
        "GPLAY": "GPLAY", "PLAY": "PLAY",
        "HGTV": "HGTV",
        "HIDI": "HIDI",
        "HIST": "HIST",
        "HLMK": "HLMK",
        "HS": "HTSR", "HTSR": "HTSR",
        "ID": "ID",
        "IFC": "IFC",
        "IFX": "IFX",
        "INA": "INA",
        "IP": "iP",
        "IQIYI": "iQIYI",
        "ITV": "ITV", "ITVX": "ITVX",
        "JOYN": "JOYN",
        "KAYO": "KAYO",
        "KCW": "KCW",
        "KKTV": "KKTV",
        "KNOW": "KNOW",
        "KNPY": "KNPY",
        "KS": "KS",
        "LIFE": "LIFE",
        "LN": "LN",
        "LOOKE": "LOOKE",
        "MBC": "MBC",
        "MGG": "MGG",
        "MNBC": "MNBC",
        "MTOD": "MTOD",
        "MTV": "MTV",
        "MUBI": "MUBI",
        "NATG": "NATG",
        "NBA": "NBA",
        "NBC": "NBC",
        "NBLA": "NBLA",
        "NFB": "NFB",
        "NFL": "NFL", "NFLN": "NFLN",
        "NICK": "NICK",
        "NOW": "NOW",
        "NRK": "NRK",
        "ODK": "ODK",
        "OPTO": "OPTO",
        "ORF": "ORF",
        "OWN": "OWN",
        "PA": "PA",
        "PBS": "PBS", "PBSK": "PBSK",
        "PKO": "PKO",
        "PLTV": "PLTV",
        "PLUZ": "PLUZ",
        "POGO": "POGO",
        "PSN": "PSN",
        "PUHU": "PUHU",
        "QIBI": "QIBI",
        "RED": "RED",
        "RKTN": "RKTN",
        "RNET": "RNET",
        "ROKU": "ROKU",
        "RSTR": "RSTR",
        "RTE": "RTE",
        "RTLP": "RTLP",
        "RUUTU": "RUUTU",
        "SBS": "SBS",
        "SCI": "SCI",
        "SESO": "SESO",
        "SHAHID": "SHAHID",
        "SHMI": "SHMI",
        "SHO": "SHO",
        "SKST": "SKST",
        "SNET": "SNET",
        "SONY": "SONY",
        "SPIK": "SPIK", "SPKE": "SPKE",
        "SPRT": "SPRT",
        "STAN": "STAN",
        "STARZ": "STARZ", "STZ": "STZ",
        "STRP": "STRP",
        "SVT": "SVT",
        "SWEET": "SWEET",
        "SWER": "SWER",
        "SYFY": "SYFY",
        "TBS": "TBS",
        "TEN": "TEN",
        "TF": "TF",
        "TFOU": "TFOU",
        "TIMV": "TIMV",
        "TLC": "TLC",
        "TOU": "TOU",
        "TRVL": "TRVL",
        "TUBI": "TUBI",
        "TV3": "TV3", "TV4": "TV4",
        "TVING": "TVING",
        "TVL": "TVL",
        "TVNZ": "TVNZ",
        "UFC": "UFC",
        "UKTV": "UKTV",
        "UNIV": "UNIV",
        "USAN": "USAN",
        "VH1": "VH1",
        "VIAP": "VIAP",
        "VICE": "VICE",
        "VIKI": "VIKI",
        "VLCT": "VLCT",
        "VMEO": "VMEO", "VIMEO": "VIMEO",
        "VMAX": "VMAX",
        "VONE": "VONE",
        "VRV": "VRV",
        "VUDU": "VUDU",
        "WAVVE": "WAVVE",
        "WME": "WME",
        "WNET": "WNET",
        "WOWP": "WOWP",
        "WWEN": "WWEN",
        "XBOX": "XBOX",
        "XUMO": "XUMO",
        "YHOO": "YHOO",
        "YT": "YT",
        "ZDF": "ZDF",
        "ZEE5": "ZEE5",
    }
    for key, value in services.items():
        if re.search(rf'\b{re.escape(key)}\b', fn):
            return value
    return ""


def detect_release_group(filename: str) -> str:
    base = os.path.splitext(filename)[0]
    match = re.search(r'-([A-Za-z0-9]+)$', base)
    if match: return match.group(1)
    return ""


def detect_dual_audio(mi_data: dict[str, Any]) -> str:
    tracks = mi_data.get("media", {}).get("track", [])
    audio_tracks = [
        t for t in tracks
        if t.get("@type") == "Audio"
        and "commentary" not in str(t.get("Title", "")).lower()
    ]
    if len(audio_tracks) < 2: return ""
    langs = set()
    for t in audio_tracks:
        lang = (t.get("Language", "") or "").lower()[:2]
        if lang: langs.add(lang)
    if len(langs) >= 2: return "Dual-Audio"
    return ""


def parse_filename(filename: str) -> dict[str, Any]:
    basename = os.path.splitext(os.path.basename(filename))[0]
    guess = guessit_module.guessit(basename, {"excludes": ["country", "language"]})
    return dict(guess)


def enrich_with_tvdb(info_dict: dict[str, Any], tvdb_client, force_tvdb_id: Optional[int] = None) -> dict[str, Any]:
    """Enrich file info with TVDB data (title, year, episode title)."""
    title = info_dict.get("title", "")
    if not title and not force_tvdb_id:
        return info_dict

    season = info_dict.get("season")
    episode = info_dict.get("episode")
    year = info_dict.get("year")

    try:
        if force_tvdb_id:
            # If we have a forced ID, get either series or movie info directly
            # Note: We don't know for sure if it's a series or movie yet from just ID, 
            # but usually users select from search results which tell us the type.
            # tvdb_client.lookup doesn't support force_id yet, let's implement the logic here
            # or update lookup. Let's update lookup in tvdb_client later or handle it here.
            
            # For now, let's assume if season/episode exists, it's a series.
            is_series = season is not None or episode is not None
            
            if is_series:
                best = tvdb_client.get_series(force_tvdb_id)
                best_type = "series"
            else:
                best = tvdb_client.get_movie(force_tvdb_id)
                best_type = "movie"
                
            tvdb_data = {
                "tvdb_id": force_tvdb_id,
                "tvdb_title": best.get("name") or best.get("nameTranslations", [""])[0],
                "tvdb_year": best.get("year", ""),
                "tvdb_type": best_type
            }
            
            # IMDb ID
            remote_ids = best.get("remoteIds") or []
            for rid in remote_ids:
                if rid.get("sourceName") == "IMDB":
                    tvdb_data["tvdb_imdb_id"] = rid.get("id")
                    break
            
            # Episode title
            if is_series and season is not None and episode is not None:
                ep = tvdb_client.find_episode(force_tvdb_id, int(season), int(episode))
                if ep:
                    tvdb_data["tvdb_episode_title"] = ep.get("name", "")
        else:
            tvdb_data = tvdb_client.lookup(
                title=title,
                season=int(season) if season else None,
                episode=int(episode) if episode else None,
                year=str(year) if year else None,
            )
    except Exception:
        return info_dict

    if not tvdb_data:
        return info_dict

    # Override title if TVDB returned one
    if tvdb_data.get("tvdb_title"):
        tv_title = tvdb_data["tvdb_title"]
        tv_year = str(tvdb_data.get("tvdb_year") or "")
        
        # If title ends with (Year) and it matches the year field, strip it
        if tv_year and tv_title.endswith(f" ({tv_year})"):
            tv_title = tv_title[:-(len(tv_year) + 3)].strip()
            
        info_dict["title"] = tv_title

    # Override year if TVDB returned one and guessit didn't find any
    if tvdb_data.get("tvdb_year") and not info_dict.get("year"):
        info_dict["year"] = tvdb_data["tvdb_year"]

    # Override episode title if TVDB returned one
    if tvdb_data.get("tvdb_episode_title"):
        info_dict["episode_title"] = tvdb_data["tvdb_episode_title"]

    # Store TVDB metadata for UI display
    info_dict["tvdb_matched"] = True
    info_dict["tvdb_id"] = tvdb_data.get("tvdb_id", "")
    if tvdb_data.get("tvdb_imdb_id"):
        info_dict["tvdb_imdb_id"] = tvdb_data["tvdb_imdb_id"]

    return info_dict


def _sanitize_title(title: str) -> str:
    """Sanitize title for scene-style filenames.
    Rules: spaces→dots, remove special chars, keep hyphens.
    """
    title = title.strip()
    # Replace & with 'and' (scene convention)
    title = title.replace(" & ", " and ")
    # Replace middle dot (WALL·E → WALL-E)
    title = title.replace("·", "-")
    # Remove apostrophes/quotes (It's → Its, C'mon → Cmon)
    title = re.sub(r"[''ʼ`\"]", "", title)
    # Transliterate accented chars to ASCII (Amélie → Amelie, Pokémon → Pokemon)
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    # Spaces to dots
    title = title.replace(" ", ".")
    # Remove all non-alphanumeric except dots and hyphens
    title = re.sub(r"[^a-zA-Z0-9.\-]", "", title)
    # Collapse multiple dots
    title = re.sub(r"\.{2,}", ".", title)
    # Remove leading/trailing dots
    title = title.strip(".")
    return title


def build_name(info: dict[str, Any]) -> str:
    """Build standardized torrent filename using PTP-like unified order."""
    parts: list[str] = []
    
    # 1. Title
    parts.append(_sanitize_title(info.get("title", "")))
    
    # 2. Year (for Movies) / SxxExx (for TV)
    year = info.get("year")
    if year:
        parts.append(str(year))
        
    s = info.get("season")
    e = info.get("episode")
    if s:
        s_str = f"S{int(s):02d}" if str(s).isdigit() else str(s)
        if e:
            e_str = f"E{int(e):02d}" if str(e).isdigit() else str(e)
            parts.append(f"{s_str}{e_str}")
        else:
            parts.append(s_str)
    elif e:
        parts.append(f"E{int(e):02d}" if str(e).isdigit() else str(e))

    # 3. Episode Title (for TV)
    ep_title = info.get("episode_title")
    if ep_title:
        parts.append(_sanitize_title(ep_title))

    # 4. Edition
    edition = info.get("edition")
    if edition:
        parts.append(edition)

    # 5. Technical attributes
    res = info.get("resolution")
    hdr = info.get("hdr")
    uhd = info.get("uhd")
    source = info.get("source")
    service = info.get("service")
    mtype = info.get("type")
    vcodec = info.get("video_encode")
    # PTP uses DUAL generally
    dual = "DUAL" if info.get("dual_audio") else ""
    acodec = info.get("audio_codec")
    atmos = info.get("audio_atmos")
    channels = info.get("audio_channels")
    hybrid = info.get("hybrid")
    repack = info.get("repack")

    if res: parts.append(res)
    if hdr: parts.append(hdr)
    if uhd: parts.append(uhd)
    # Skip source "WEB" when type is already WEB-DL or WEBRip (redundant)
    if source and not (source == "WEB" and mtype in ("WEBDL", "WEBRIP")):
        parts.append(source)
    if service and mtype in ("WEBDL", "WEBRIP"): parts.append(service)
    
    # Type (REMUX, WEB-DL, etc.)
    if mtype == "REMUX":
        parts.append("REMUX")
    elif mtype == "WEBDL":
        parts.append("WEB-DL")
    elif mtype == "WEBRIP":
        parts.append("WEBRip")
    elif mtype and mtype != "ENCODE":
        parts.append(mtype)

    # Audio section (before video codec, per scene naming convention)
    # Short codecs combine with channels: DDP5.1, DD2.0, AAC2.0
    _COMBINED_CODECS = {"DD", "DDP", "AAC"}
    if acodec:
        if channels and acodec in _COMBINED_CODECS:
            parts.append(f"{acodec}{channels}")
        else:
            parts.append(acodec)
            if channels: parts.append(channels)
        if atmos: parts.append(atmos)
    elif channels:
        parts.append(channels)

    if dual: parts.append(dual)

    # Video codec
    if vcodec: parts.append(vcodec)
    
    # Final flags
    if hybrid: parts.append(hybrid)
    if repack: parts.append(repack)

    name = ".".join(p for p in parts if p)
    name = re.sub(r'\.{2,}', '.', name)
    tag = info.get("tag", "")
    if tag:
        name = f"{name}-{tag}"
    return name


def process_file(filepath: str, tag_override: Optional[str] = None, tvdb_client=None, force_tvdb_id: Optional[int] = None, mode: str = 'tv') -> dict[str, Any]:
    filepath = os.path.abspath(filepath)
    mi_data = extract_mediainfo(filepath)
    guess = parse_filename(filepath)
    v_track = _get_track(mi_data, "Video")
    a_track = _get_best_audio_track(mi_data)
    source, mtype = detect_source_type(filepath)
    res = detect_resolution(v_track)
    v_enc, v_codec = detect_video_encode(v_track, mtype)
    a_info = detect_audio(a_track)

    # Resolve conflicting Episode Title
    ep_title = guess.get("episode_title")
    if ep_title:
        # If episode title is one of the tags, it's not a title
        bad_tags = ["DUB", "SUB", "DUAL", "REPACK", "PROPER", "REMUX", "BluRay", "1080p", "720p", "2160p"]
        if ep_title.upper() in bad_tags:
            ep_title = ""
    
    # Fallback for missing MediaInfo (e.g. dummy files or failed extract)
    if not res: res = guess.get("screen_size")
    if not source: 
        s_guess = guess.get("source")
        if s_guess: source = s_guess.replace(" ", "")
    if mtype == "ENCODE" and not mtype:
        m_guess = guess.get("type")
        if m_guess: mtype = m_guess.upper()

    if not a_info['audio_codec']:
        gc = guess.get("audio_codec")
        if gc:
            for k, v in AUDIO_COMMERCIAL_MAP.items():
                if k.lower() in gc.lower():
                    gc = v
                    break
            a_info['audio_codec'] = gc
            
    if not v_codec:
        vc = guess.get("video_codec")
        if vc:
            if vc.lower() == "x264": v_codec = "h.264"
            elif vc.lower() == "x265": v_codec = "h.265"
            else: v_codec = vc

    if not v_enc:
        ve = guess.get("video_encode")
        if ve: v_enc = ve

    info_dict = {
        "title": guess.get("title", "Unknown"),
        "episode_title": ep_title,
        "year": guess.get("year", ""),
        "season": guess.get("season", ""),
        "episode": guess.get("episode", ""),
        "resolution": res,
        "source": source,
        "type": mtype,
        "uhd": detect_uhd(mtype, res, source),
        "hdr": detect_hdr(v_track) or (guess.get("video_profile") if "HDR" in str(guess.get("video_profile")) else ""),
        "audio_codec": a_info["audio_codec"],
        "audio_channels": a_info["audio_channels"],
        "audio_atmos": a_info["audio_atmos"],
        "video_encode": v_enc,
        "video_codec": v_codec,
        "hybrid": detect_hybrid(filepath),
        "repack": detect_repack(filepath),
        "edition": detect_edition(filepath),
        "service": detect_service(filepath),
        "dual_audio": detect_dual_audio(mi_data) or ("dual" in filepath.lower() or "dual" in str(guess.get("audio_channels", "")).lower()),
        "tag": tag_override or guess.get("release_group", "")
    }

    # If guessit picked up the streaming service as the release group, clear it
    if not tag_override and info_dict["tag"] and info_dict["service"]:
        if info_dict["tag"].upper() == info_dict["service"].upper():
            info_dict["tag"] = ""

    # In movie mode, clear TV-specific fields to avoid guessit false positives
    if mode == 'movie':
        info_dict["season"] = ""
        info_dict["episode"] = ""
        info_dict["episode_title"] = ""

    # Enrich with TVDB data if client is provided
    if tvdb_client:
        info_dict = enrich_with_tvdb(info_dict, tvdb_client, force_tvdb_id=force_tvdb_id)

    return {"filepath": filepath, "old_name": os.path.basename(filepath),
            "new_name": build_name(info_dict) + os.path.splitext(filepath)[1], "info": info_dict}


def process_directory(dirpath: str, tag_override: Optional[str] = None, tvdb_client=None, force_tvdb_id: Optional[int] = None, mode: str = 'tv') -> dict[str, Any]:
    """Process all video files in a directory and suggest a folder name."""
    dirpath = os.path.abspath(dirpath)
    results = []
    video_exts = {".mkv", ".mp4", ".ts", ".avi"}
    
    # 1. Process files
    for entry in sorted(os.listdir(dirpath)):
        if os.path.splitext(entry)[1].lower() not in video_exts: continue
        if "sample" in entry.lower() and "!sample" not in entry.lower(): continue
        try:
            results.append(process_file(os.path.join(dirpath, entry), tag_override, tvdb_client=tvdb_client, force_tvdb_id=force_tvdb_id, mode=mode))
        except Exception as e:
            results.append({"filepath": os.path.join(dirpath, entry), "old_name": entry, "new_name": None, "error": str(e)})
            
    # 2. Suggest folder name based on the first successful result
    suggested_folder = ""
    valid_results = [r for r in results if r.get("new_name")]
    if valid_results:
        # Use info from the first file
        first_info = valid_results[0]["info"].copy()
        
        # If multiple files exist and they look like a TV series, 
        # the folder should probably NOT have the episode number/title
        if len(valid_results) > 1 and first_info.get("episode"):
            first_info["episode"] = ""
            first_info["episode_title"] = ""
            
        suggested_folder = build_name(first_info)
        
    return {
        "dirpath": dirpath,
        "old_folder": os.path.basename(dirpath),
        "new_folder": suggested_folder,
        "files": results
    }


def rename_file(filepath: str, new_name: str) -> tuple[bool, str]:
    """Rename a single file. Returns (success, error_message)."""
    try:
        target = os.path.join(os.path.dirname(filepath), new_name)
        if os.path.exists(target):
            return False, f"File already exists: {new_name}"
        os.rename(filepath, target)
        return True, ""
    except Exception as e:
        return False, str(e)


def rename_directory(dirpath: str, new_name: str) -> tuple[bool, str]:
    """Rename a directory. Returns (success, error_message_or_new_path)."""
    try:
        dirpath = os.path.abspath(dirpath)
        parent = os.path.dirname(dirpath)
        new_path = os.path.join(parent, new_name)
        if os.path.exists(new_path):
            return False, f"Directory already exists: {new_name}"
        os.rename(dirpath, new_path)
        return True, new_path
    except Exception as e:
        return False, str(e)
