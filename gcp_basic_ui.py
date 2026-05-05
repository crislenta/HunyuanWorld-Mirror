import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import gradio as gr


REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("HWM_OUTPUT_ROOT", "/tmp/hunyuan-world-mirror")).resolve()
MAX_UPLOADS = int(os.environ.get("HWM_MAX_UPLOADS", "24"))
DEFAULT_TARGET_SIZE = int(os.environ.get("HWM_TARGET_SIZE", "518"))
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".webm", ".gif"}
IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def _coerce_upload_path(file_value) -> Path:
    if isinstance(file_value, (str, os.PathLike)):
        return Path(file_value)
    if isinstance(file_value, dict) and "name" in file_value:
        return Path(file_value["name"])
    name = getattr(file_value, "name", None)
    if name:
        return Path(name)
    raise ValueError(f"Unsupported uploaded file object: {type(file_value)!r}")


def _copy_uploads(files: list) -> tuple[Path, Path, list[Path]]:
    if not files:
        raise gr.Error("Upload at least one image or video.")
    if len(files) > MAX_UPLOADS:
        raise gr.Error(f"Upload at most {MAX_UPLOADS} files for one run.")

    job_dir = OUTPUT_ROOT / f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    upload_dir = job_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    copied_paths = []
    for index, file_value in enumerate(files):
        source = _coerce_upload_path(file_value)
        suffix = source.suffix.lower()
        if suffix not in IMAGE_EXTENSIONS and suffix not in VIDEO_EXTENSIONS:
            raise gr.Error(f"Unsupported file type: {source.name}")
        destination = upload_dir / f"{index:03d}{suffix}"
        shutil.copy2(source, destination)
        copied_paths.append(destination)

    video_paths = [path for path in copied_paths if path.suffix.lower() in VIDEO_EXTENSIONS]
    image_paths = [path for path in copied_paths if path.suffix.lower() in IMAGE_EXTENSIONS]
    if video_paths and image_paths:
        raise gr.Error("Use either images or videos for a run, not both.")

    input_path = video_paths[0] if len(video_paths) == 1 else upload_dir
    return job_dir, input_path, copied_paths


def _collect_outputs(job_dir: Path) -> dict:
    result_dirs = [path for path in job_dir.glob("results/*") if path.is_dir()]
    if not result_dirs:
        raise RuntimeError("Inference finished without creating an output directory.")
    result_dir = max(result_dirs, key=lambda path: path.stat().st_mtime)

    depth_images = sorted((result_dir / "depth").glob("*.png"))
    normal_images = sorted((result_dir / "normal").glob("*.png"))
    resized_images = sorted((result_dir / "images_resized").glob("*.png"))
    rendered_videos = sorted((result_dir / "rendered").glob("*.mp4"))
    downloadable_files = [
        path
        for path in [
            result_dir / "pts_from_pointmap.ply",
            result_dir / "gaussians.ply",
            result_dir / "sparse" / "0" / "points3D.ply",
        ]
        if path.exists()
    ]

    archive_base = job_dir / "hunyuan-world-mirror-output"
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", result_dir))
    downloadable_files.append(archive_path)

    return {
        "result_dir": result_dir,
        "depth_images": [str(path) for path in depth_images],
        "normal_images": [str(path) for path in normal_images],
        "resized_images": [str(path) for path in resized_images],
        "rendered_video": str(rendered_videos[0]) if rendered_videos else None,
        "downloadable_files": [str(path) for path in downloadable_files],
    }


def run_hunyuan_world_mirror(
    files,
    fps: int,
    target_size: int,
    confidence_percentile: float,
    edge_normal_threshold: float,
    edge_depth_threshold: float,
    apply_sky_mask: bool,
    render_video: bool,
):
    job_dir, input_path, copied_paths = _copy_uploads(files or [])
    results_dir = job_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(REPO_ROOT / "infer.py"),
        "--input_path",
        str(input_path),
        "--output_path",
        str(results_dir),
        "--fps",
        str(int(fps)),
        "--target_size",
        str(int(target_size)),
        "--confidence_percentile",
        str(float(confidence_percentile)),
        "--edge_normal_threshold",
        str(float(edge_normal_threshold)),
        "--edge_depth_threshold",
        str(float(edge_depth_threshold)),
    ]
    if not render_video:
        command.append("--skip_rendered")
    if apply_sky_mask:
        command.append("--apply_sky_mask")

    process = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_output = process.stdout[-12000:]
    if process.returncode != 0:
        raise gr.Error(f"Inference failed with exit code {process.returncode}.\n\n{log_output}")

    outputs = _collect_outputs(job_dir)
    uploaded_preview = [str(path) for path in copied_paths if path.suffix.lower() in IMAGE_EXTENSIONS]
    status = (
        f"Completed. Output directory: {outputs['result_dir']}\n\n"
        f"Command: {' '.join(command)}\n\n"
        f"{log_output}"
    )
    return (
        status,
        uploaded_preview or outputs["resized_images"],
        outputs["depth_images"],
        outputs["normal_images"],
        outputs["rendered_video"],
        outputs["downloadable_files"],
    )


with gr.Blocks(title="HunyuanWorld-Mirror Basic UI") as demo:
    gr.Markdown(
        """
        # HunyuanWorld-Mirror basic GCP UI

        Upload a small image sequence or one video, run reconstruction, then download the generated depth,
        normal, point cloud, Gaussian splat, COLMAP, and rendered outputs. The first run downloads model
        weights from Hugging Face unless they are already cached in the container volume.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            uploads = gr.File(
                label="Images or one video",
                file_count="multiple",
                file_types=["image", "video"],
                type="filepath",
            )
            fps = gr.Slider(1, 8, value=1, step=1, label="Video extraction FPS")
            target_size = gr.Slider(224, 728, value=DEFAULT_TARGET_SIZE, step=14, label="Model target size")
            confidence_percentile = gr.Slider(0, 50, value=10, step=1, label="Confidence percentile filter")
            edge_normal_threshold = gr.Slider(0, 30, value=5, step=0.5, label="Normal edge threshold")
            edge_depth_threshold = gr.Slider(0, 0.2, value=0.03, step=0.005, label="Depth edge threshold")
            apply_sky_mask = gr.Checkbox(value=False, label="Apply sky mask")
            render_video = gr.Checkbox(
                value=os.environ.get("HWM_RENDER_VIDEO", "false").lower() == "true",
                label="Render camera path video (requires CUDA)",
            )
            run_button = gr.Button("Run reconstruction", variant="primary")

        with gr.Column(scale=2):
            status = gr.Textbox(label="Run log", lines=16)
            rendered_video = gr.Video(label="Rendered camera path")
            downloads = gr.File(label="Downloads", file_count="multiple")

    with gr.Tab("Uploaded / resized images"):
        uploaded_gallery = gr.Gallery(label="Input preview", columns=4, height=360)
    with gr.Tab("Depth"):
        depth_gallery = gr.Gallery(label="Depth maps", columns=4, height=360)
    with gr.Tab("Normals"):
        normal_gallery = gr.Gallery(label="Normal maps", columns=4, height=360)

    run_button.click(
        fn=run_hunyuan_world_mirror,
        inputs=[
            uploads,
            fps,
            target_size,
            confidence_percentile,
            edge_normal_threshold,
            edge_depth_threshold,
            apply_sky_mask,
            render_video,
        ],
        outputs=[status, uploaded_gallery, depth_gallery, normal_gallery, rendered_video, downloads],
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
        ssr_mode=False,
    )
