"""--soundfix's rewriter: a sound started only while GetSoundPlaying says it isn't playing gets its own state
(a flag for a loop, a one-frame-early timer for a one-shot); anything it can't prove safe is left alone."""
import pytest

import mwdialog_soundfix as SF   # noqa: E402  (conftest put the tools on sys.path)
from conftest import m          # noqa: F401  (loads the tools)

LEN = {"plx_wa_cloudy": 48.45, "bell": 10.0}.get


def rw(text, mode="flag"):
    return SF.rewrite(text.replace("\n", "\r\n"), LEN, mode)


BOAT = """begin Sound_Boat_Creak

short done

if ( CellChanged == 0 )
\tif ( GetSoundPlaying "Boat Creak" == 0 )
\t\tPlayLoopSound3DVP "Boat Creak" 0.4, 1.0
\tendif
endif

end
"""


def test_a_guarded_loop_becomes_a_flag_declared_after_the_authors_locals():
    new, groups = rw(BOAT)
    lines = new.split("\r\n")
    assert groups == [{"var": "mwsfOn1", "kind": "loop", "ref": "", "sounds": ["boat creak"]}]
    assert lines.index("short done") < lines.index(next(ln for ln in lines if ln.startswith("short mwsfEp")))
    assert any(ln.startswith("\tif ( mwsfOn1 == 0 )") and 'was ( GetSoundPlaying "Boat Creak" == 0 )' in ln for ln in lines)
    play = next(i for i, ln in enumerate(lines) if "PlayLoopSound3DVP" in ln)
    assert lines[play + 1].strip().startswith("set mwsfOn1 to 1")
    assert "if ( mwsfEp != MWSF_Epoch )" in new and "StopSound" not in new and "CellChanged == 1" not in new
    assert "GetSoundPlaying" not in "\r\n".join(SF.split_comment(ln)[0] for ln in lines)


def test_restart_mode_stops_before_starting_and_rearms_on_cell_change():
    new, _g = rw(BOAT, "restart")
    lines = new.split("\r\n")
    play = next(i for i, ln in enumerate(lines) if "PlayLoopSound3DVP" in ln)
    assert lines[play - 1].strip().startswith('StopSound "Boat Creak"')
    assert "if ( CellChanged == 1 )" in new


def test_a_guarded_one_shot_becomes_a_timer_one_frame_early_divided_by_pitch():
    new, groups = rw('begin W\nif ( GetSoundPlaying "plx_WA_cloudy" == 0 )\n\tPlaySound3DVP "plx_WA_cloudy", 0.70, 2.0\nendif\nend\n')
    assert groups[0]["kind"] == "timer" and groups[0]["var"] == "mwsfT1"
    assert "if ( mwsfT1 <= 0 )" in new
    assert "set mwsfT1 to ( 24.2250 - GetSecondsPassed )" in new
    assert "set mwsfT1 to ( mwsfT1 - GetSecondsPassed )" in new


def test_is_playing_checks_and_stopsound_follow_the_state():
    src = """begin Swamp
if ( gamehour > 20 )
\tif ( GetSoundPlaying "swampNight" == 0 )
\t\tPlayLoopSound3DVP "swampNight", 1.0, 1.0
\tendif
else
\tif ( GetSoundPlaying "swampNight" )
\t\tStopSound, "swampNight"
\tendif
endif
end
"""
    new, _g = rw(src)
    lines = new.split("\r\n")
    assert any(ln.strip().startswith("if ( mwsfOn1 == 1 )") for ln in lines)
    stop = next(i for i, ln in enumerate(lines) if "StopSound" in ln)
    assert lines[stop + 1].strip().startswith("set mwsfOn1 to 0")


def test_a_family_guard_shares_one_flag_and_a_reference_is_kept():
    src = """begin Plains
if ( Player->GetSoundPlaying "plainsNL5" == 0 )
\tPlayer->PlayLoopSound3DVP "plainsNL", 1.0, 1.0
endif
if ( Player->GetSoundPlaying "plainsNL" == 1 )
\tset x to 1
endif
end
"""
    new, groups = rw(src)
    assert groups[0]["ref"] == "player" and groups[0]["sounds"] == ["plainsnl", "plainsnl5"]
    assert "if ( mwsfOn1 == 1 )" in new


def test_late_declarations_and_a_stray_endif_are_handled_like_the_cs():
    src = 'begin A\nset x to 1\nshort x\nendif\nif ( GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nendif\nend\n'
    new, _g = rw(src)
    lines = new.split("\r\n")
    assert lines.index("short x") < lines.index(next(ln for ln in lines if ln.startswith("short mwsfEp")))
    assert lines.index(next(ln for ln in lines if ln.startswith("short mwsfEp"))) < lines.index("if ( mwsfOn1 == 0 )    "
                                                                                                 '; MWSoundFix: was ( GetSoundPlaying "x" == 0 )')


@pytest.mark.parametrize("src, why", [
    ('begin A\nif ( GetSoundPlaying "nolength" == 0 )\n\tPlaySound3D "nolength"\nendif\nend\n', "no length"),
    ('begin A\nif ( GetSoundPlaying "bell" == 0 )\n\tPlaySound3DVP "bell", 1.0, pitchvar\nendif\nend\n', "pitch"),
    ('begin A\nif ( GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nendif\nshort late\nend\n', "after statements"),
    ('begin A\nif ( MenuMode )\n\treturn\nendif\nshort late\nif ( GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nendif\nend\n',
     "after a 'return'"),
    ('begin A\nif ( GetSoundPlaying "bell" == 0 )\n\tPlayLoopSound3D "bell"\n\tPlaySound3D "bell"\nendif\nend\n', "both"),
    ('begin A\nshort mwsfOn1\nif ( GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nendif\nend\n', "mwsf"),
    ('begin A\nif ( "Boat"->GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nendif\nend\n', "another reference"),
    ('begin A\nif ( GetSoundPlaying "x" == 0 )\n\tPlayLoopSound3D "x"\nend\n', "never closed"),
    ('begin A\nif ( GetSoundPlaying "x" == 1 )\n\tStopSound "x"\nendif\nend\n', "no play under"),
])
def test_what_it_cant_prove_safe_is_left_alone(src, why):
    with pytest.raises(SF.Skip, match=why):
        rw(src)


NESTED = """begin Swamp
if ( GetSoundPlaying "a" == 0 )
\tif ( GetSoundPlaying "b" == 0 )
\t\tPlayLoopSound3D "a"
\tendif
endif
if ( GetSoundPlaying "a" == 0 )
\tif ( GetSoundPlaying "b" == 0 )
\t\tPlayLoopSound3D "b"
\tendif
endif
if ( GetSoundPlaying "a" )
\tStopSound "a"
elseif ( GetSoundPlaying "b" )
\tStopSound "b"
endif
end
"""


def test_nested_guards_give_every_played_sound_its_own_state():
    new, groups = rw(NESTED)
    assert [(g["var"], g["sounds"]) for g in groups] == [("mwsfOn1", ["a"]), ("mwsfOn2", ["b"])]
    lines = [SF.split_comment(ln)[0].strip() for ln in new.split("\r\n")]
    assert lines.count("if ( mwsfOn1 == 0 )") == 2 and lines.count("if ( mwsfOn2 == 0 )") == 2
    assert "if ( mwsfOn1 == 1 )" in lines and "elseif ( mwsfOn2 == 1 )" in lines
    assert lines[lines.index('StopSound "b"') + 1] == "set mwsfOn2 to 0"


def test_nested_guards_on_a_sound_the_script_never_plays_are_left_alone():
    src = 'begin A\nif ( GetSoundPlaying "x" == 0 )\n\tif ( GetSoundPlaying "y" == 0 )\n\t\tPlayLoopSound3D "y"\n' \
          '\tendif\nendif\nif ( GetSoundPlaying "y" == 0 )\n\tPlayLoopSound3D "y"\nendif\nend\n'
    with pytest.raises(SF.Skip, match="never plays"):
        rw(src)
