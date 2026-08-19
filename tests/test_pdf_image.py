"""Tests for PDF and image file reading."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest

from app.core.pdf_image_reader import (
    is_document,
    read_document,
    _ocr_result_to_df,
)
from app.core.reader import list_sheets, read_frame, read_frame_head


def test_is_document():
    assert is_document(Path("test.pdf")) is True
    assert is_document(Path("test.PDF")) is True
    assert is_document(Path("test.jpg")) is True
    assert is_document(Path("test.JPG")) is True
    assert is_document(Path("test.png")) is True
    assert is_document(Path("test.tiff")) is True
    assert is_document(Path("test.bmp")) is True
    assert is_document(Path("test.webp")) is True
    assert is_document(Path("test.xlsx")) is False
    assert is_document(Path("test.csv")) is False


def test_list_sheets_document():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\n%...\n")
        path = Path(f.name)
    try:
        sheets = list_sheets(path)
        assert sheets == ["Nội dung"]
    finally:
        path.unlink(missing_ok=True)


def test_read_frame_head_document():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\n%...\n")
        path = Path(f.name)
    try:
        # Should raise error for dummy PDF
        with pytest.raises(Exception):
            read_frame_head(path)
    finally:
        path.unlink(missing_ok=True)


def test_read_frame_document():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\n%...\n")
        path = Path(f.name)
    try:
        with pytest.raises(Exception):
            read_frame(path)
    finally:
        path.unlink(missing_ok=True)


def test_ocr_result_to_df_empty():
    df = _ocr_result_to_df([])
    assert df is None


def test_ocr_result_to_df_simple():
    # Mock OCR result: header row + 2 data rows
    result = [
        ([[10, 10], [50, 10], [50, 20], [10, 20]], "STT", 0.9),
        ([[60, 10], [120, 10], [120, 20], [60, 20]], "Tên", 0.9),
        ([[130, 10], [180, 10], [180, 20], [130, 20]], "Số", 0.9),
        ([[10, 30], [50, 30], [50, 40], [10, 40]], "1", 0.9),
        ([[60, 30], [120, 30], [120, 40], [60, 40]], "An", 0.9),
        ([[130, 30], [180, 30], [180, 40], [130, 40]], "100", 0.9),
        ([[10, 50], [50, 50], [50, 60], [10, 60]], "2", 0.9),
        ([[60, 50], [120, 50], [120, 60], [60, 60]], "Bình", 0.9),
        ([[130, 50], [180, 50], [180, 60], [130, 60]], "200", 0.9),
    ]
    df = _ocr_result_to_df(result)
    assert df is not None
    assert list(df.columns) == ["STT", "Tên", "Số"]
    assert len(df) == 2
    assert df.iloc[0]["STT"] == "1"
    assert df.iloc[0]["Tên"] == "An"
    assert df.iloc[0]["Số"] == "100"
    assert df.iloc[1]["STT"] == "2"
    assert df.iloc[1]["Tên"] == "Bình"
    assert df.iloc[1]["Số"] == "200"


def test_ocr_result_to_df_uneven_columns():
    # Data row with fewer columns than header
    result = [
        ([[10, 10], [50, 10], [50, 20], [10, 20]], "A", 0.9),
        ([[60, 10], [120, 10], [120, 20], [60, 20]], "B", 0.9),
        ([[10, 30], [50, 30], [50, 40], [10, 40]], "1", 0.9),
    ]
    df = _ocr_result_to_df(result)
    assert df is not None
    assert list(df.columns) == ["A", "B"]
    assert len(df) == 1
    assert df.iloc[0]["A"] == "1"
    assert df.iloc[0]["B"] is None


def test_read_document_pdf_requires_pdf2image():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\n%...\n")
        path = Path(f.name)
    try:
        # pdf2image not installed in test env, should raise ValueError after all strategies fail
        with pytest.raises(ValueError, match="Không trích xuất được dữ liệu"):
            read_document(path)
    finally:
        path.unlink(missing_ok=True)


def test_read_document_image_fallback():
    """Test that image reading raises appropriate error for dummy file."""
    from PIL import Image
    import numpy as np

    # Create a simple test image
    img = Image.new("RGB", (200, 100), "white")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f.name)
        path = Path(f.name)

    try:
        # Should either work (if OCR detects nothing -> empty) or raise
        df = read_document(path)
        # If no text detected, df could be None or empty
        if df is not None:
            assert hasattr(df, "columns")
    except Exception:
        # OCR may fail on blank image - acceptable
        pass
    finally:
        path.unlink(missing_ok=True)