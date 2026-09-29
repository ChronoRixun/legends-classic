"""Record what the default speaker is playing (WASAPI loopback) and report loudness per second.

usage: record_audio.py <out.wav> <seconds>
"""
import sys, wave
import numpy as np
import soundcard as sc

RATE = 44100


def main(path, seconds):
    speaker = sc.default_speaker()
    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
    data = mic.record(samplerate=RATE, numframes=int(RATE * seconds))
    pcm = np.clip(data, -1, 1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((pcm * 32767).astype('<i2').tobytes())
    mono = pcm.mean(axis=1)
    per_sec = [float(np.sqrt(np.mean(mono[i:i + RATE] ** 2))) for i in range(0, len(mono), RATE)]
    print('rms per second (dBFS):', ' '.join(f'{20 * np.log10(max(r, 1e-9)):.0f}' for r in per_sec))


if __name__ == '__main__':
    main(sys.argv[1], float(sys.argv[2]))
