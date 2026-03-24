"""PTP Standard Naming Tests."""

from renamer_logic import build_name


def test_ptp_remux_movie():
    """Test: PTP-style Movie REMUX"""
    info = {
        "title": "Spider-Man: No Way Home",
        "year": "2021",
        "resolution": "2160p",
        "hdr": "DV.HDR10",
        "uhd": "UHD",
        "source": "BluRay",
        "type": "REMUX",
        "video_encode": "HEVC",
        "audio_codec": "TrueHD",
        "audio_atmos": "Atmos",
        "audio_channels": "7.1",
        "hybrid": "HYBRID",
        "tag": "FraMeSToR",
    }
    result = build_name(info)
    print(f"PTP Movie REMUX: {result}")
    expected = "Spider-Man.No.Way.Home.2021.2160p.DV.HDR10.UHD.BluRay.REMUX.HEVC.TrueHD.Atmos.7.1.HYBRID-FraMeSToR"
    status = "✓" if result == expected else "✗"
    print(f"  {status} PTP Movie Standard")
    print()


def test_ptp_remux_anime():
    """Test: PTP-style Anime REMUX (Alya example)"""
    info = {
        "title": "Alya Sometimes Hides Her Feelings in Russian",
        "season": "1",
        "episode": "3",
        "episode_title": "And So They Met",
        "resolution": "1080p",
        "source": "BluRay",
        "type": "REMUX",
        "video_encode": "AVC",
        "dual_audio": "Dual-Audio",
        "audio_codec": "FLAC",
        "audio_channels": "2.0",
        "tag": "NAN0",
    }
    result = build_name(info)
    print(f"PTP Anime REMUX: {result}")
    expected = "Alya.Sometimes.Hides.Her.Feelings.in.Russian.S01E03.And.So.They.Met.1080p.BluRay.REMUX.AVC.DUAL.FLAC.2.0-NAN0"
    status = "✓" if result == expected else "✗"
    print(f"  {status} PTP Anime Standard")
    print()


def test_ptp_webdl_movie():
    """Test: PTP-style WEB-DL"""
    info = {
        "title": "Wednesday",
        "year": "2022",
        "season": "1",
        "episode": "1",
        "resolution": "2160p",
        "hdr": "DV.HDR",
        "source": "WEB",
        "service": "NF",
        "type": "WEBDL",
        "video_encode": "H.265",
        "audio_codec": "DD+",
        "audio_atmos": "Atmos",
        "audio_channels": "5.1",
        "tag": "FLUX",
    }
    result = build_name(info)
    print(f"PTP WEB-DL:      {result}")
    expected = "Wednesday.2022.S01E01.2160p.DV.HDR.WEB.NF.WEB-DL.H.265.DD+.Atmos.5.1-FLUX"
    status = "✓" if result == expected else "✗"
    print(f"  {status} PTP WEB-DL Standard")
    print()


if __name__ == "__main__":
    print("=" * 80)
    print("VMF Renamer – PTP Standard Naming Verification")
    print("=" * 80)
    print()

    test_ptp_remux_movie()
    test_ptp_remux_anime()
    test_ptp_webdl_movie()

    print("=" * 80)
    print("All tests complete.")
