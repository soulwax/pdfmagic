import os

import pypdfium2 as pdfium


def rasterize_pdf(input_path: str, output_dir: str, dpi: int = 300) -> list[str]:
    pdf = pdfium.PdfDocument(input_path)
    scale = dpi / 72
    output_paths = []
    for page_number in range(len(pdf)):
        page = pdf[page_number]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        output_path = os.path.join(output_dir, f"page_{page_number:04d}.png")
        image.save(output_path)
        output_paths.append(output_path)
    return output_paths
