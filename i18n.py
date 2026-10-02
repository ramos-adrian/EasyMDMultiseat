"""
Lightweight gettext wrapper.

Source strings are English; translations live in locale/<lang>/LC_MESSAGES/multiseat-manager.mo
(generated from locale/<lang>.po by tools/i18n.py). Use `from i18n import _`.
"""

import gettext
import os
from pathlib import Path

DOMAIN = "multiseat-manager"
LOCALE_DIR = Path(__file__).resolve().parent / "locale"
SUPPORTED = ("en", "es")

_translation = gettext.NullTranslations()


def setup(lang=None):
    """
    Activates translations. `lang` (e.g. "es") overrides the environment;
    otherwise LANGUAGE/LC_ALL/LC_MESSAGES/LANG are honored. Falls back to English.
    """
    global _translation
    if lang:
        os.environ["LANGUAGE"] = lang
    localedir = LOCALE_DIR if LOCALE_DIR.is_dir() else None
    _translation = gettext.translation(DOMAIN, localedir=localedir, fallback=True)


def _(message):
    return _translation.gettext(message)


setup()
