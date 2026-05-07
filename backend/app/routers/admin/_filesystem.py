import os


def _dir_size_mb(path: str) -> float:
    if not os.path.isdir(path):
        return 0.0
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)


def _prune_excluded(root: str, dirs: list[str], exclude_abs: str | None) -> None:
    """Drop subdirectories that match the excluded absolute path so os.walk skips them."""
    if not exclude_abs:
        return
    dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(root, d)) != exclude_abs]


def _count_files(path: str, exclude: str | None = None) -> int:
    if not os.path.isdir(path):
        return 0
    exclude_abs = os.path.abspath(exclude) if exclude else None
    path_abs = os.path.abspath(path)
    n = 0
    for root, dirs, files in os.walk(path_abs):
        _prune_excluded(root, dirs, exclude_abs)
        n += len(files)
    return n


def _dir_size_mb_excluding(path: str, exclude: str | None) -> float:
    """Like _dir_size_mb but skips the `exclude` subtree (resolved absolute)."""
    if not os.path.isdir(path):
        return 0.0
    exclude_abs = os.path.abspath(exclude) if exclude else None
    path_abs = os.path.abspath(path)
    total = 0
    for root, dirs, files in os.walk(path_abs):
        _prune_excluded(root, dirs, exclude_abs)
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)
