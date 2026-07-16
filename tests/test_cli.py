import os
from pathlib import Path

import pdfbetter.cli as cli_module
from pdfbetter.cli import main


def test_cli_writes_output_pdf(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path])

    assert exit_code == 0
    assert os.path.exists(output_path)
    captured = capsys.readouterr()
    assert "wrote" in captured.out


def test_cli_reports_failure_for_missing_input(tmp_path, capsys):
    exit_code = main([str(tmp_path / "does-not-exist.pdf"), "-o", str(tmp_path / "out.pdf")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "failed to process" in captured.err


def test_cli_audit_flag_writes_report(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--audit"])

    assert exit_code == 0
    assert os.path.exists(f"{output_path}.audit.json")
    captured = capsys.readouterr()
    assert "audit report" in captured.out


def test_cli_custom_threshold_flag_is_applied(synthetic_pdf_path, tmp_path):
    import pdfplumber

    output_path = str(tmp_path / "output.pdf")
    main([synthetic_pdf_path, "-o", output_path, "--bg-threshold", "1.5"])

    with pdfplumber.open(output_path) as pdf:
        assert len(pdf.pages[0].rects) == 1


def test_cli_warns_but_succeeds_on_unimproved_page(background_only_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([background_only_pdf_path, "-o", output_path])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "left unchanged" in captured.err


def test_cli_defaults_output_to_existing_output_dir(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    exit_code = main([synthetic_pdf_path])

    assert exit_code == 0
    expected = tmp_path / "output" / f"{Path(synthetic_pdf_path).stem}_printerfriendly.pdf"
    assert expected.exists()


def test_cli_defaults_output_to_documents_folder_when_no_output_dir(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    exit_code = main([synthetic_pdf_path])

    assert exit_code == 0
    expected = fake_home / "Documents" / "PDFBETTER OUTPUT" / f"{Path(synthetic_pdf_path).stem}_printerfriendly.pdf"
    assert expected.exists()


def test_cli_explicit_output_still_overrides_default(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit_path = str(tmp_path / "explicit.pdf")

    exit_code = main([synthetic_pdf_path, "-o", explicit_path])

    assert exit_code == 0
    assert os.path.exists(explicit_path)
    assert not (tmp_path / "output").exists()


def test_cli_rejects_surgery_flags_with_rasterize_mode(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--mode", "rasterize", "--audit"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "surgery-mode-only" in captured.err


def test_cli_rasterize_mode_reports_missing_extra_cleanly(monkeypatch, synthetic_pdf_path, tmp_path, capsys):
    def fake_import():
        raise ImportError("No module named 'pypdfium2'")

    monkeypatch.setattr(cli_module, "_import_process_rasterize_upscale", fake_import)

    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--mode", "rasterize"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "pip install pdfbetter[rasterize]" in captured.err


def test_cli_rasterize_mode_success_path_passes_all_flags_through(monkeypatch, synthetic_pdf_path, tmp_path, capsys):
    from pdfbetter.rasterize_upscale_pipeline import RasterizeUpscaleResult

    captured_kwargs = {}

    def fake_process(input_path, output_path, **kwargs):
        captured_kwargs.update(kwargs)
        with open(output_path, "wb") as f:
            f.write(b"%PDF-fake")
        return RasterizeUpscaleResult(output_path=output_path, pages_processed=3)

    monkeypatch.setattr(cli_module, "_import_process_rasterize_upscale", lambda: fake_process)

    output_path = str(tmp_path / "output.pdf")
    exit_code = main(
        [
            synthetic_pdf_path,
            "-o",
            output_path,
            "--mode",
            "rasterize",
            "--render-dpi",
            "150",
            "--crop-x",
            "10",
            "--crop-y",
            "20",
            "--realesrgan-model",
            "realesrgan-x4plus-anime",
            "--realesrgan-tile",
            "128",
            "--realesrgan-threads",
            "2:4:4",
            "--realesrgan-tta",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "wrote" in captured.out
    assert os.path.exists(output_path)
    assert captured_kwargs["dpi"] == 150
    assert captured_kwargs["crop_x"] == 10.0
    assert captured_kwargs["crop_y"] == 20.0
    assert captured_kwargs["model"] == "realesrgan-x4plus-anime"
    assert captured_kwargs["tile"] == 128
    assert captured_kwargs["threads"] == "2:4:4"
    assert captured_kwargs["tta"] is True
