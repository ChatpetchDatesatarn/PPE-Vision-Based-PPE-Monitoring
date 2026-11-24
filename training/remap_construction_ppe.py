"""
Convert the Ultralytics Construction-PPE dataset (YOLO format, 11 classes)
to the 4 project classes per training/classes.txt:

    0 person   <- Person (6)
    1 helmet   <- helmet (0)
    2 vest     <- vest (2)
    3 head     <- no_helmet (7)   # "head" = head not wearing a helmet

Other classes (gloves, boots, goggles, none, no_goggle, no_gloves, no_boots) are dropped.
Images left with no boxes are kept as background (negative samples).

Dataset: https://docs.ultralytics.com/datasets/detect/construction-ppe/
License AGPL-3.0 — must be cited in the report (Dalvi et al., 2025)

Usage:
    python remap_construction_ppe.py <dataset_folder_after_unzip> <output_folder>
e.g.
    python remap_construction_ppe.py construction-ppe ..\\01_dataset\\public_datasets\\construction-ppe-4cls
"""
import shutil
import sys
from collections import Counter
from pathlib import Path

MAP = {6: 0, 0: 1, 2: 2, 7: 3}
NAMES = ["person", "helmet", "vest", "head"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main(src: Path, dst: Path):
    if not (src / "images").is_dir():
        sys.exit(f"Folder {src / 'images'} not found — point to the folder that contains images/ and labels/")

    total = Counter()
    for split in ("train", "val", "test"):
        img_dir, lbl_dir = src / "images" / split, src / "labels" / split
        if not img_dir.is_dir():
            continue
        out_img, out_lbl = dst / "images" / split, dst / "labels" / split
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        n_img = n_bg = 0
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in IMG_EXT:
                continue
            lines = []
            lbl = lbl_dir / (img.stem + ".txt")
            if lbl.exists():
                for raw in lbl.read_text().splitlines():
                    parts = raw.split()
                    if len(parts) < 5:
                        continue
                    cls = int(float(parts[0]))
                    if cls in MAP:
                        new = MAP[cls]
                        lines.append(" ".join([str(new)] + parts[1:5]))
                        total[(split, new)] += 1
            shutil.copy2(img, out_img / img.name)
            (out_lbl / (img.stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
            n_img += 1
            n_bg += not lines
        print(f"{split:5s}: {n_img} images ({n_bg} background-only)")

    (dst / "classes.txt").write_text("\n".join(NAMES) + "\n")
    (dst / "data.yaml").write_text(
        f"path: {dst.resolve().as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(NAMES))
    )

    print("\nBoxes per class:")
    print(f"{'class':8s} {'train':>6s} {'val':>6s} {'test':>6s}")
    for i, n in enumerate(NAMES):
        print(f"{n:8s} {total[('train', i)]:6d} {total[('val', i)]:6d} {total[('test', i)]:6d}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
