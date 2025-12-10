"""Tests for text extractors."""

import pytest
from pathlib import Path

from scrubiq.classifier.extractors.base import ExtractionError
from scrubiq.classifier.extractors.registry import ExtractorRegistry
from scrubiq.classifier.extractors.text import TextExtractor


class TestTextExtractor:
    @pytest.fixture
    def extractor(self):
        return TextExtractor()

    def test_extensions_include_common_types(self, extractor):
        exts = extractor.extensions
        assert ".txt" in exts
        assert ".csv" in exts
        assert ".json" in exts
        assert ".md" in exts
        assert ".py" in exts
        assert ".sql" in exts
        assert ".env" in exts

    def test_can_handle_txt(self, extractor):
        assert extractor.can_handle(Path("test.txt"))
        assert extractor.can_handle(Path("TEST.TXT"))
        assert extractor.can_handle(Path("test.csv"))

    def test_cannot_handle_docx(self, extractor):
        assert not extractor.can_handle(Path("test.docx"))

    def test_extract_utf8(self, extractor, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World! SSN: 078-05-1120", encoding="utf-8")

        text = extractor.extract(test_file)
        assert "Hello, World!" in text
        assert "078-05-1120" in text

    def test_extract_utf8_bom(self, extractor, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"\xef\xbb\xbfHello BOM")

        text = extractor.extract(test_file)
        assert "Hello BOM" in text

    def test_extract_latin1_fallback(self, extractor, tmp_path):
        test_file = tmp_path / "test.txt"
        # Write some latin-1 specific bytes
        test_file.write_bytes(b"Hello \xe9\xe8\xe0")  # éèà in latin-1

        text = extractor.extract(test_file)
        assert "Hello" in text

    def test_extract_nonexistent_file(self, extractor, tmp_path):
        with pytest.raises(ExtractionError):
            extractor.extract(tmp_path / "nonexistent.txt")


class TestExtractorRegistry:
    @pytest.fixture
    def registry(self):
        return ExtractorRegistry()

    def test_can_extract_txt(self, registry):
        assert registry.can_extract(Path("test.txt"))

    def test_can_extract_docx(self, registry):
        assert registry.can_extract(Path("test.docx"))

    def test_can_extract_xlsx(self, registry):
        assert registry.can_extract(Path("test.xlsx"))

    def test_can_extract_pdf(self, registry):
        assert registry.can_extract(Path("test.pdf"))

    def test_can_extract_pptx(self, registry):
        assert registry.can_extract(Path("test.pptx"))

    def test_can_extract_msg(self, registry):
        assert registry.can_extract(Path("test.msg"))

    def test_can_extract_rtf(self, registry):
        assert registry.can_extract(Path("test.rtf"))

    def test_can_extract_eml(self, registry):
        assert registry.can_extract(Path("test.eml"))

    def test_cannot_extract_unknown(self, registry):
        assert not registry.can_extract(Path("test.xyz"))
        assert not registry.can_extract(Path("test.exe"))

    def test_extract_unknown_raises_error(self, registry, tmp_path):
        test_file = tmp_path / "test.xyz"
        test_file.write_text("test")

        with pytest.raises(ExtractionError) as exc_info:
            registry.extract(test_file)
        assert ".xyz" in str(exc_info.value)

    def test_extract_txt_via_registry(self, registry, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("SSN: 078-05-1120")

        text = registry.extract(test_file)
        assert "078-05-1120" in text

    def test_supported_extensions(self, registry):
        exts = registry.supported_extensions
        # Should include extensions from all extractors
        assert ".txt" in exts
        assert ".docx" in exts
        assert ".xlsx" in exts
        assert ".pdf" in exts
        assert ".pptx" in exts
        assert ".msg" in exts
        assert ".rtf" in exts
        assert ".eml" in exts
        # Should be sorted and unique
        assert exts == sorted(set(exts))

    def test_case_insensitive_extension(self, registry):
        assert registry.can_extract(Path("test.TXT"))
        assert registry.can_extract(Path("test.DOCX"))
        assert registry.can_extract(Path("test.PDF"))


class TestExtractorIntegration:
    """Integration tests that actually create and extract from files."""

    @pytest.fixture
    def registry(self):
        return ExtractorRegistry()

    def test_extract_csv(self, registry, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,ssn\nJohn Smith,078-05-1120\n")

        text = registry.extract(csv_file)
        assert "John Smith" in text
        assert "078-05-1120" in text

    def test_extract_json(self, registry, tmp_path):
        json_file = tmp_path / "data.json"
        json_file.write_text('{"employee": {"ssn": "078-05-1120"}}')

        text = registry.extract(json_file)
        assert "078-05-1120" in text

    def test_extract_env(self, registry, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=sk-secret123\nPASSWORD=hunter2")

        text = registry.extract(env_file)
        assert "sk-secret123" in text
        assert "hunter2" in text

    def test_extract_sql(self, registry, tmp_path):
        sql_file = tmp_path / "query.sql"
        sql_file.write_text("SELECT * FROM users WHERE ssn = '078-05-1120';")

        text = registry.extract(sql_file)
        assert "078-05-1120" in text
