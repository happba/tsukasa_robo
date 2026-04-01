from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class ScheduleImageService:
    def __init__(self, font_path: Path) -> None:
        self.font_path = font_path

    def render(self, data: list[list[str]], colors: dict[tuple[int, int], dict[str, tuple[int, int, int]]]) -> Path:
        if not data:
            raise ValueError("Cannot render an empty schedule.")

        try:
            font = ImageFont.truetype(str(self.font_path), 18)
        except OSError:
            font = ImageFont.load_default()

        row_height = 30
        col_width = 120
        padding = 10
        width = padding * 2 + col_width * len(data[0])
        height = padding * 2 + row_height * len(data)
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        for row_index, row in enumerate(data):
            y = padding + row_index * row_height
            for col_index, cell in enumerate(row):
                x = padding + col_index * col_width
                cell_colors = colors.get((row_index, col_index), {"background": (255, 255, 255), "text": (0, 0, 0)})
                draw.rectangle(
                    [x, y, x + col_width, y + row_height],
                    fill=cell_colors["background"],
                    outline=(0, 0, 0),
                )
                text = str(cell)
                bbox = draw.textbbox((0, 0), text, font=font)
                text_x = x + (col_width - (bbox[2] - bbox[0])) / 2
                text_y = y + (row_height - (bbox[3] - bbox[1])) / 2
                draw.text((text_x, text_y), text, fill=cell_colors["text"], font=font)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            output = Path(tmp_file.name)
        image.save(output)
        return output

