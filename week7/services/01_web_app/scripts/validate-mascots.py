"""Read-only atlas geometry check. Requires Pillow; never edits source art."""
from pathlib import Path
from PIL import Image

expected = [7, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]
root = Path(__file__).resolve().parents[1] / "public" / "mascots"
for path in sorted(root.glob("*.webp")):
    image = Image.open(path)
    assert image.size == (1536, 2288), path
    assert image.mode == "RGBA", path
    alpha = image.getchannel("A")
    assert alpha.getextrema() == (0, 255), path
    for row, count in enumerate(expected):
        occupied = [column for column in range(8) if alpha.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208)).getbbox()]
        assert occupied == list(range(count)), (path, row, occupied)
    print("PASS", path.name, "geometry / transparency / animation cells")
assert len(list(root.glob("*.webp"))) == 5
