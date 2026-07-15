import os
from pathlib import Path

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
