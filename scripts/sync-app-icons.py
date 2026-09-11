"""Import an existing ICO without redrawing it; export its largest frame for Tauri."""
import argparse
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    public = ROOT / "apps/desktop/public"
    public.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as icon:
        if icon.format != "ICO":
            raise ValueError("请输入 ICO 图标")
        size = max(icon.ico.sizes(), key=lambda item: item[0] * item[1])
        frame = icon.ico.getimage(size).convert("RGBA")
        frame.save(public / "app-icon.png")
        # Explicit native window icon, independent of installer/shortcut caches.
        native = frame.resize((32, 32), Image.Resampling.LANCZOS)
        (ROOT / "apps/desktop/src-tauri/icons/taskbar-icon.rgba").write_bytes(native.tobytes())
    shutil.copyfile(source, public / "app-icon.ico")
    print(f"Imported original ICO and {size[0]}x{size[1]} PNG frame.")


if __name__ == "__main__":
    main()
