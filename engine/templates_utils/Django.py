#!/usr/bin/env python3
import glob
import os
import re
from pathlib import Path
from typing import Optional


def resolve_settings_path() -> Optional[Path]:
    module = os.environ.get("DJANGO_SETTINGS_MODULE", "").strip()
    candidates: list[Path] = []
    if module:
        candidates.append(Path("/app") / (module.replace(".", "/") + ".py"))
    for path in glob.glob("/app/**/settings.py", recursive=True):
        candidates.append(Path(path))
    return next((candidate for candidate in candidates if candidate.exists()), None)


def patch_whitenoise(settings_path: Path) -> bool:
    text = settings_path.read_text(encoding="utf-8")
    updated = text

    middleware_line = "    'whitenoise.middleware.WhiteNoiseMiddleware',"
    if "whitenoise.middleware.WhiteNoiseMiddleware" not in updated:
        pattern = r"(?s)(MIDDLEWARE\s*=\s*\[)(.*?)(\])"
        match = re.search(pattern, updated)
        if match:
            body = match.group(2).rstrip()
            # WhiteNoise should be close to the top, ideally right after SecurityMiddleware.
            if "'django.middleware.security.SecurityMiddleware'," in body:
                body = body.replace(
                    "'django.middleware.security.SecurityMiddleware',",
                    "'django.middleware.security.SecurityMiddleware',\n"
                    + middleware_line,
                    1,
                )
                if not body.endswith("\n"):
                    body += "\n"
            else:
                body = f"{body}\n{middleware_line}\n" if body else f"\n{middleware_line}\n"
            updated = (
                updated[: match.start()]
                + match.group(1)
                + body
                + match.group(3)
                + updated[match.end() :]
            )

    if "STATIC_URL" not in updated:
        updated = updated.rstrip() + "\n\nSTATIC_URL = '/static/'\n"

    if "STATIC_ROOT" not in updated:
        updated = (
            updated.rstrip()
            + "\n\nSTATIC_ROOT = str(BASE_DIR).rstrip('/') + '/staticfiles'\n"
        )

    if "STORAGES" not in updated and "STATICFILES_STORAGE" not in updated:
        updated = (
            updated.rstrip()
            + "\n\nSTATICFILES_STORAGE = "
            + "'whitenoise.storage.CompressedManifestStaticFilesStorage'\n"
        )
    elif "STORAGES" in updated and "whitenoise.storage.CompressedManifestStaticFilesStorage" not in updated:
        updated = (
            updated.rstrip()
            + "\n\n"
            + "try:\n"
            + "    STORAGES\n"
            + "except NameError:\n"
            + "    STORAGES = {}\n"
            + "STORAGES.setdefault(\n"
            + "    'staticfiles',\n"
            + "    {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},\n"
            + ")\n"
        )

    if updated != text:
        settings_path.write_text(updated, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    settings_path = resolve_settings_path()
    if not settings_path:
        print("WhiteNoise patch: settings.py not found; skipping.")
        raise SystemExit(0)

    changed = patch_whitenoise(settings_path)
    if changed:
        print(f"WhiteNoise patch applied to {settings_path}")
    else:
        print("WhiteNoise patch: already configured or no editable MIDDLEWARE list.")
