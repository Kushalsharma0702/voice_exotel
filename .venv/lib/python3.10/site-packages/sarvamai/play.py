import base64
import shutil
import subprocess
import wave
from .types.text_to_speech_response import TextToSpeechResponse


def is_installed(lib_name: str) -> bool:
    lib = shutil.which(lib_name)
    if lib is None:
        return False
    return True


def play(
    audio: TextToSpeechResponse, 
    notebook: bool = False, 
    use_ffmpeg: bool = True
) -> None:
    af_str = "".join(audio.audios)
    af_bytes = base64.b64decode(af_str)
    if notebook:
        try:
            from IPython.display import Audio, display  # type: ignore
        except ModuleNotFoundError:
            message = (
                "`pip install ipython` required when `notebook=False` "
            )
            raise ValueError(message)

        display(Audio(af_bytes, rate=22050, autoplay=True))
    elif use_ffmpeg:
        if not is_installed("ffplay"):
            message = (
                "ffplay from ffmpeg not found, necessary to play audio. "
                "On mac you can install it with 'brew install ffmpeg'. "
                "On linux and windows you can install it from "
                "https://ffmpeg.org/"
            )
            raise ValueError(message)
        args = ["ffplay", "-autoexit", "-", "-nodisp"]
        proc = subprocess.Popen(
            args=args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate(input=af_bytes)
        proc.poll()
    else:
        try:
            import io

            import sounddevice as sd  # type: ignore
            import soundfile as sf  # type: ignore
        except ModuleNotFoundError:
            message = (
                "`pip install sounddevice soundfile` required when "
                "`use_ffmpeg=False` "
            )
            raise ValueError(message)
        sd.play(*sf.read(io.BytesIO(af_bytes)))
        sd.wait()


def save(audio: TextToSpeechResponse, filename: str) -> None:
    if isinstance(audio.audios, list):
        combined_audio = "".join(audio.audios)
        b64_file = base64.b64decode(combined_audio)

        with open(filename, "wb") as f:
            f.write(b64_file)
