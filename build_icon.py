"""Builds the macOS icon set (`images/icon.icns`) from `images/icon.svg`.

The SVG is rendered at every size macOS asks for, and the PNGs are
assembled into an `.icns` file with `iconutil`.
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

# The sizes macOS expects in an `.iconset` folder.
SIZES = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]

ICON_DIRECTORY = Path(__file__).parent / 'images'
SOURCE_SVG = ICON_DIRECTORY / 'icon.svg'
ICONSET_DIRECTORY = ICON_DIRECTORY / 'icon.iconset'
OUTPUT_ICNS = ICON_DIRECTORY / 'icon.icns'


def render_svg(size: int) -> QImage:
    """Renders the SVG at `size` pixels, on a transparent background."""
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer = QSvgRenderer(str(SOURCE_SVG))
    renderer.render(painter)
    painter.end()
    return image


def build_iconset() -> None:
    """Writes the PNGs of the icon set."""
    ICONSET_DIRECTORY.mkdir(exist_ok=True)
    for size, scale in SIZES:
        image = render_svg(size * scale)
        suffix = '' if scale == 1 else '@2x'
        path = ICONSET_DIRECTORY / f'icon_{size}x{size}{suffix}.png'
        if not image.save(str(path)):
            raise RuntimeError(f'could not write {path}')


def build_icns() -> None:
    """Assembles the icon set into the `.icns` file."""
    subprocess.run(
        ['iconutil', '-c', 'icns', str(ICONSET_DIRECTORY), '-o',
         str(OUTPUT_ICNS)],
        check=True)
    print(f'wrote {OUTPUT_ICNS} ({OUTPUT_ICNS.stat().st_size} bytes)')


def main() -> int:
    QApplication([])
    build_iconset()
    build_icns()
    return 0


if __name__ == '__main__':
    sys.exit(main())
