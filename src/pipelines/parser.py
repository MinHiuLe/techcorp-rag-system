import io
import os
import logging
import tempfile
from pathlib import Path

# Lightweight parsing libraries
try:
    import pymupdf4llm
except ImportError:
    pymupdf4llm = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    from pptx import Presentation as PptxPresentation
except ImportError:
    PptxPresentation = None

logger = logging.getLogger(__name__)

class LightweightDocumentParser:
    """
    A lightweight parser tailored for environments with limited resources (like laptops).
    Uses pymupdf4llm for PDF, python-docx for DOCX, and python-pptx for PPTX.
    Outputs structured Markdown optimized for LLM chunking.
    """
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.pptx'}

    def parse(self, file_bytes: bytes, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        if ext == '.pdf':
            return self._parse_pdf(file_bytes)
        elif ext == '.docx':
            return self._parse_docx(file_bytes)
        elif ext == '.pptx':
            return self._parse_pptx(file_bytes)

    def _parse_pdf(self, file_bytes: bytes) -> str:
        if not pymupdf4llm:
            raise RuntimeError("pymupdf4llm is not installed. Please run 'pip install pymupdf4llm'")
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            md_text = pymupdf4llm.to_markdown(tmp_path)
            return md_text
        except Exception as e:
            logger.error(f"Failed to parse PDF using pymupdf4llm: {e}")
            raise
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _parse_docx(self, file_bytes: bytes) -> str:
        if not DocxDocument:
            raise RuntimeError("python-docx is not installed. Please run 'pip install python-docx'")
        try:
            doc = DocxDocument(io.BytesIO(file_bytes))
            md_lines = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                style_name = para.style.name.lower()
                if 'heading 1' in style_name:
                    md_lines.append(f"# {text}")
                elif 'heading 2' in style_name:
                    md_lines.append(f"## {text}")
                elif 'heading 3' in style_name:
                    md_lines.append(f"### {text}")
                else:
                    md_lines.append(text)
            
            for table in doc.tables:
                for idx, row in enumerate(table.rows):
                    row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                    md_lines.append("| " + " | ".join(row_data) + " |")
                    if idx == 0:
                        separator = ["---"] * len(row.cells)
                        md_lines.append("| " + " | ".join(separator) + " |")
                md_lines.append("")

            return "\n\n".join(md_lines)
        except Exception as e:
            logger.error(f"Failed to parse DOCX: {e}")
            raise

    def _parse_pptx(self, file_bytes: bytes) -> str:
        if not PptxPresentation:
            raise RuntimeError("python-pptx is not installed. Please run 'pip install python-pptx'")
        try:
            prs = PptxPresentation(io.BytesIO(file_bytes))
            md_lines = []
            for slide_num, slide in enumerate(prs.slides, 1):
                md_lines.append(f"## Slide {slide_num}")
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        text = shape.text.strip()
                        if text:
                            md_lines.append(text)
                md_lines.append("\n---")
            return "\n\n".join(md_lines)
        except Exception as e:
            logger.error(f"Failed to parse PPTX: {e}")
            raise
