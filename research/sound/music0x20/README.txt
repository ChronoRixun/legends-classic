XML1 layered music (sample flag 0x20) -> XML2 PC
==================================================

WHAT 0x20 MEANS (same design in both engines)
  A sample with 0x20 holds TWO stereo sub-streams ("layers") of equal length, played in sync on two voices of one
  stream. Layer 0 is the base track. Layer 1 is a combat layer that is added on top.
  - XML1: all 29 layered _c banks split cleanly at 32768 frames (join jump 0.85-1.26, where 1.0 = seamless).
    Layer 0 contains the zone's _a material in 23 of 29 banks (r=0.43-0.95). Layer 1 never correlates with _a
    (|r| <= 0.03), and layer 0 vs layer 1 is ~0. See layer_vs_a.json.
  - XML2 ships 37 layered _c banks (flags 0x22, 22050 Hz), e.g. abug_c, new_c, sewer_c, boss1_c.
    The "XML2 ships no 0x20 sample" note was wrong. town1-5_c are plain 0x02 streams.
    survey_flags.py lists them all.

  Music start (identical code in both games): 'music/<soundfile>_c' and '_a' are looked up
  (XMen2 0x477690 / XML1 0x7a88d-0x7aa23). The _c stream is started if a game-state check passes and _c exists,
  otherwise _a (XMen2 0x4782bd / XML1 0x7b081).
  Cross-fader (XMen2 0x477010 / XML1 0x7a300, same logic):
    state 2 = not in combat: voice 0 at full, voice 1 silent
    state 3 = combat: voice 0 + voice 1
  XMen2 applies the volumes through vtable slot 0x1c -> 0x58fea0 -> 0x58ff00 -> 0x5958d0, which calls
  IDirectSoundBuffer::SetVolume per sub-voice buffer.

HOW THE ENGINES STREAM IT
  XML1 default.xbe:
    0x191b66  sub-voice count = (flags & 0x20) ? 2 : 1, channels = (flags & 2) ? 2 : 1
    0x193953  chunk per sub-voice = 0x4800 bytes (nBlockAlign 0x24, mono) or 0x9000 bytes (0x48, stereo)
              = 512 Xbox-ADPCM blocks = 32768 frames
    0x192620  each read = nsub * 0x9000 bytes; 0x192750 submits one packet per sub-voice. The data confirms
              that chunk i of each read belongs to sub-voice i: the layers split at 32768 frames are seamless.
              Each voice's chunks are self-contained Xbox-ADPCM blocks.
  XML2 XMen2.exe:
    0x59610a  sub-voice count = (flags & 0x20) ? 2 : 1; one DirectSound buffer per sub-voice (0x59622e),
              at least 0x8dc00 bytes (0x596135)
    0x595d60  refill: decode nsub * 0x8000 PCM bytes with 0x595b20, then bytes [i*0x8000, (i+1)*0x8000) go to
              voice i, i.e. 8192 stereo frames per voice per refill. A final partial read of `got` bytes gives
              each voice got - (nsub-1)*0x8000 bytes.
    0x595b20  ONE continuous IMA ADPCM decode over the whole file. The state at +0x18/+0x20 is shared by both
              voices. It is reset to (0,0) only when the stream restarts at EOF (0x595dd0).
  Layout on disk, both games: L0 chunk0, L1 chunk0, L0 chunk1, L1 chunk1, ...
  Layer 0's last chunk is padded (zeros in XML1) and only as much of it plays as layer 1's last chunk has.
  XML2's own layered banks are encoded exactly like this, as one continuous IMA stream.
  (xml2_layout.py: decoding the layers with separate states produces garbage: DC 3000-12000, rms x10.)

WHY THE 1:1 CONVERSION FAILED
  The 1:1 conversion kept XML1's 32768-frame chunks. XML2 hands out 8192-frame slices, so out of combat it plays
    L0[0:8k], L0[16k:24k], L1[0:8k], L1[16k:24k], ...
  The in-game recording nyc1_music_only.wav matches the simulated XML2 voice 0 of that old bank at 1.000
  (median over 2 s windows). It matches the real XML1 layer 0 at only 0.23.
  nyc1_music22k.wav matches voice 0 of the 22 kHz variant at 0.993, so the engine model is confirmed in game.

THE FIX (tools/fix_music.py)
  1. Decode the Xbox original losslessly.
  2. Split it into the two layers at 32768 frames.
  3. Rebuild XML2's layout: 8192-frame chunks, L0/L1 alternating, flag 0x22 kept, rate 44100 kept
     (--rate 22050 is optional).
  4. Encode ONE continuous IMA stream from (0,0).

  Seams: the shared decoder state would click both voices at every switch. XML2's own banks do this: voice-0
  click ratio 2.9-16. The fix avoids it:
  - The tail of every layer-1 chunk is cross-faded into the layer-0 frames just before the next layer-0 chunk.
    Fade = 8 frames per 22050 Hz. The hold is chosen per seam from the IMA step index, which can only fall by
    one per sample.
  - A weighted beam search encodes around every switch.
  - As a result voice 0 (everything heard out of combat) has no seams.
  - The price is paid only in voice 1, which is heard only in combat and always on top of voice 0:
    layer 1 is replaced by layer 0 for about 0.5-2 ms every 0.19 s.

RESULTS (banks/eng, 61 banks: 29 layered + 32 plain; batch_summary.txt)
  voice 0 vs XML1 layer 0 : SNR 33.0-70.2 dB (median 53.0). The error near switches is 1.5-7.9 dB LOWER than
                            elsewhere. Click ratio 0.91-1.21 (source ~1.0).
                            Lag-0 correlation in 5 s windows (nyc1, sewer1): min 1.000.
  voice 1 vs XML1 layer 1 : SNR 17.5-24.9 dB. This comes from the deliberate seam cross-fades.
                            Correlation min 0.994 (nyc1, sewer1).
  combat mix              : SNR 21-25.6 dB. Click ratio 0.74-3.66. XML2's own banks: 1.6-3.9.
  plain _a / menu         : SNR 26-67 dB (median 56). Beam re-encode from Xbox, flags unchanged.
  Levels and spectra: nyc1 voice 0 is -24.8 dBFS rms, the same as XML1 layer 0. For comparison, XML2 town1_c is
  -25.2 and XML2's layered voice 0 is -24.2 to -28.4, so no gain change is needed.
  Old bank (1:1) voice 0: click 5.2, correlation to layer 0 0.14-0.21.
  All 61 banks re-parse strictly (zsnd.py: 0 bad). Re-running from out/all_ima inputs gives byte-identical output:
  the Xbox original is found by path.

LISTEN (wav/nyc1_c/)
  xml1_reference_layer0_out_of_combat.wav   XML1 layer 0 (what should play idle)
  FIXED_xml2_voice0_out_of_combat.wav       what XML2 plays idle from the fixed bank (should sound identical)
  xml1_reference_layer1_combat_layer_alone.wav / FIXED_xml2_voice1_combat_layer_alone.wav
  xml1_reference_layer0+1_in_combat.wav     / FIXED_xml2_voice0+1_in_combat.wav
  OLD_bank_what_xml2_played_out_of_combat.wav   what the 1:1 bank played (garbled, 60 s)

IN-GAME TEST
  Copy banks/eng/n/y/nyc1_c.zss and nyc1_a.zss to xml2_test/Sounds/eng/n/y/. They replace the 22 kHz no-flag
  test files currently installed.
  The zone world entity needs soundfile="nyc1" (not "town1").
  Record while idle, and again in combat (tools/record_audio.py). Then run:
    python tools/fix_music.py match <rec.wav> xml2_test/Sounds/eng/n/y/nyc1_c.zss --xml1 xml1_xbox/sounds/zsds/n/y/nyc1_c.zss
  Idle: the top two rows should be "XML2 voice0 (out of combat)" and "XML1 layer0 (reference, out of combat)",
    both at median ~0.9 or higher (old bank: layer0 0.23).
  Combat: "voice0+1" / "layer0+1" should rank highest.
  22 kHz alternative for A/B: banks_22k/eng/n/y/nyc1_{a,c}.zss.
  Fallback (no layering): python tools/fix_music.py fix --only nyc1 --flatten layer0

SCRIPTS HERE
  survey_flags.py    flags/rates of every music sample in both games
  analyze_layers.py  chunk-size scan (join continuity, correlation with _a)
  xml2_layout.py     shared-state vs per-layer decode of XML2's own banks
  recmatch.py        recordings vs simulated XML2 voices
  xdis.py            disassembler/grep for default.xbe (binimg) or a PE
  seam_experiment.py seam strategy comparison (hard / cross-fade / hold / head)
  validate_music.py  independent end-to-end check -> validation_<zone>.json / .txt
  layer_vs_a.py      layer 0/1 vs _a over all 29 banks
  summarize_batch.py batch table -> batch_summary.txt
  _previous_attempt/ outputs of the earlier run of this task (kept, not used)
