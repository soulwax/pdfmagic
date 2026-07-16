import os
import shutil
import subprocess


class RealesrganNotFoundError(Exception):
    pass


class RealesrganFailedError(Exception):
    pass


def find_realesrgan(explicit_path: str | None = None) -> str:
    if explicit_path:
        return explicit_path

    env_path = os.environ.get("PDFBETTER_REALESRGAN_PATH")
    if env_path:
        return env_path

    found = shutil.which("realesrgan-ncnn-vulkan")
    if found:
        return found

    raise RealesrganNotFoundError(
        "realesrgan-ncnn-vulkan not found. Install it and ensure it's on PATH, "
        "set the PDFBETTER_REALESRGAN_PATH environment variable, or pass "
        "--realesrgan-path. On Windows: 'scoop install realesrgan-ncnn-vulkan'. "
        "On macOS/Linux: download the matching release from the upstream "
        "Real-ESRGAN project's releases."
    )


def upscale_directory(
    input_dir: str,
    output_dir: str,
    *,
    binary_path: str,
    model: str = "realesrgan-x4plus",
    scale: int = 2,
    tile: int = 0,
    threads: str = "1:2:2",
    tta: bool = False,
) -> None:
    cmd = [
        binary_path,
        "-i",
        input_dir,
        "-o",
        output_dir,
        "-n",
        model,
        "-s",
        str(scale),
        "-t",
        str(tile),
        "-j",
        threads,
    ]
    if tta:
        cmd.append("-x")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RealesrganFailedError(
            f"realesrgan-ncnn-vulkan failed (exit code {result.returncode}): {result.stderr}"
        )
