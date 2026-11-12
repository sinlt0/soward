import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rpg import anims
from utils import anim_lib


def main() -> None:
    os.makedirs(anims.DIR, exist_ok=True)
    total = 0
    for key in anims.all_keys():
        data = anim_lib.render(key).getvalue()
        with open(anims.path(key), "wb") as handle:
            handle.write(data)
        total += len(data)
    print(f"{len(anims.all_keys())} animations, {total // 1024} KB")


if __name__ == "__main__":
    main()
